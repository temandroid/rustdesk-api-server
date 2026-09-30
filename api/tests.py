import base64
import datetime
import json

from django.test import TestCase, Client, override_settings

from api.models import UserProfile, RustDeskPeer, RustDeskTag, RustDeskToken, RustDeskDevice, ShareLink, ConnLog, FileLog
from api.views_front import EFFECTIVE_SECONDS, SHARELINK_EFFECTIVE_SECONDS, ONLINE_SECONDS


def api_post(client, path, data, token=None):
    headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'} if token else {}
    return client.post(path, json.dumps(data), content_type='application/json', **headers)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class BaseTestCase(TestCase):
    def setUp(self):
        self.admin = UserProfile.objects.create_superuser('admin', 'Admin-pass-123')
        self.bob = UserProfile.objects.create_user('bob', 'Bob-pass-123')
        self.alice = UserProfile.objects.create_user('alice', 'Alice-pass-123')
        self.admin_peer = RustDeskPeer.objects.create(uid=self.admin.id, rid='111', alias='admin-pc')
        self.bob_peer = RustDeskPeer.objects.create(uid=self.bob.id, rid='222', alias='bob-pc')

    def web_client(self, username, password, enforce_csrf=False):
        client = Client(enforce_csrf_checks=enforce_csrf)
        client.login(username=username, password=password)
        return client

    def api_login(self, client, username, password, rid='900', uuid='u-900'):
        resp = api_post(client, '/api/login', {'username': username, 'password': password, 'id': rid, 'uuid': uuid})
        return resp.json()['access_token']


class CsrfTests(BaseTestCase):
    def test_web_post_without_csrf_token_is_rejected(self):
        client = self.web_client('bob', 'Bob-pass-123', enforce_csrf=True)
        resp = client.post('/api/add_peer', {'clientID': '333', 'alias': 'x'})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(RustDeskPeer.objects.filter(rid='333').exists())

    def test_client_api_works_without_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        token = self.api_login(client, 'bob', 'Bob-pass-123')
        self.assertTrue(token)

    def test_delete_peer_requires_post(self):
        client = self.web_client('bob', 'Bob-pass-123')
        self.assertEqual(client.get('/api/delete_peer?rid=222').status_code, 405)
        self.assertTrue(RustDeskPeer.objects.filter(rid='222').exists())
        client.post('/api/delete_peer', {'rid': '222'})
        self.assertFalse(RustDeskPeer.objects.filter(rid='222').exists())


class AccessControlTests(BaseTestCase):
    def test_edit_peer_of_other_user_is_not_found(self):
        client = self.web_client('bob', 'Bob-pass-123')
        self.assertEqual(client.get('/api/edit_peer?rid=111').status_code, 404)
        self.assertEqual(client.get('/api/edit_peer?rid=222').status_code, 200)

    def test_admin_pages_are_forbidden_for_regular_user(self):
        client = self.web_client('bob', 'Bob-pass-123')
        for path in ('/api/assign_peer?rid=111', '/api/conn_log', '/api/file_log'):
            self.assertEqual(client.get(path).status_code, 302, path)
        client.post('/api/assign_peer', {'uid': self.bob.id, 'clientID': '111', 'alias': 'stolen'})
        self.assertFalse(RustDeskPeer.objects.filter(rid='111', uid=self.bob.id).exists())

    def test_admin_pages_are_available_for_admin(self):
        client = self.web_client('admin', 'Admin-pass-123')
        for path in ('/api/assign_peer?rid=111', '/api/conn_log', '/api/file_log'):
            self.assertEqual(client.get(path).status_code, 200, path)

    def test_registration_is_disabled(self):
        resp = Client().post('/api/user_action?action=register', {'user': 'mallory', 'pwd': 'Mallory-pass-1'})
        self.assertEqual(resp.status_code, 405)
        self.assertFalse(UserProfile.objects.filter(username='mallory').exists())


class ShareLinkTests(BaseTestCase):
    def make_link(self, **kwargs):
        return ShareLink.objects.create(uid=self.bob.id, shash='link-hash', peers='222', **kwargs)

    def test_get_does_not_redeem_link(self):
        self.make_link()
        client = self.web_client('alice', 'Alice-pass-123')
        self.assertEqual(client.get('/api/share/link-hash').status_code, 200)
        self.assertFalse(ShareLink.objects.get(shash='link-hash').is_used)
        self.assertFalse(RustDeskPeer.objects.filter(uid=self.alice.id).exists())

    def test_link_can_be_redeemed_only_once(self):
        self.make_link()
        alice = self.web_client('alice', 'Alice-pass-123')
        alice.post('/api/share/link-hash')
        self.assertTrue(RustDeskPeer.objects.filter(uid=self.alice.id, rid='222').exists())

        admin = self.web_client('admin', 'Admin-pass-123')
        resp = admin.post('/api/share/link-hash')
        self.assertContains(resp, 'does not exist or has expired')
        self.assertFalse(RustDeskPeer.objects.filter(uid=self.admin.id, rid='222').exists())

    def test_expired_link_is_rejected(self):
        link = self.make_link()
        old = datetime.datetime.now() - datetime.timedelta(seconds=SHARELINK_EFFECTIVE_SECONDS + 1)
        ShareLink.objects.filter(id=link.id).update(create_time=old)
        client = self.web_client('alice', 'Alice-pass-123')
        resp = client.post('/api/share/link-hash')
        self.assertContains(resp, 'does not exist or has expired')
        self.assertFalse(RustDeskPeer.objects.filter(uid=self.alice.id).exists())

    def test_message_is_escaped(self):
        RustDeskPeer.objects.create(uid=self.bob.id, rid='<script>x</script>', alias='evil')
        ShareLink.objects.create(uid=self.bob.id, shash='xss-hash', peers='<script>x</script>')
        client = self.web_client('alice', 'Alice-pass-123')
        resp = client.post('/api/share/xss-hash')
        self.assertNotContains(resp, '<script>x</script>')
        self.assertContains(resp, '&lt;script&gt;')

    def test_created_link_hash_is_random(self):
        client = self.web_client('bob', 'Bob-pass-123')
        data = json.dumps([{'title': '222|bob-pc'}])
        first = client.post('/api/share', {'data': data}).json()['shash']
        second = client.post('/api/share', {'data': data}).json()['shash']
        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 40)


class ClientApiTests(BaseTestCase):
    def test_expired_token_is_rejected(self):
        client = Client()
        token = self.api_login(client, 'bob', 'Bob-pass-123')
        self.assertIn('data', client.get('/api/ab', HTTP_AUTHORIZATION=f'Bearer {token}').json())

        old = datetime.datetime.now() - datetime.timedelta(seconds=EFFECTIVE_SECONDS + 1)
        RustDeskToken.objects.filter(access_token=token).update(create_time=old)
        self.assertIn('error', client.get('/api/ab', HTTP_AUTHORIZATION=f'Bearer {token}').json())

    def test_heartbeat_extends_token_but_not_into_future(self):
        client = Client()
        token = self.api_login(client, 'bob', 'Bob-pass-123', rid='900', uuid='u-900')
        old = datetime.datetime.now() - datetime.timedelta(seconds=EFFECTIVE_SECONDS - 60)
        RustDeskToken.objects.filter(access_token=token).update(create_time=old)
        api_post(client, '/api/heartbeat', {'id': '900', 'uuid': 'u-900'})
        create_time = RustDeskToken.objects.get(access_token=token).create_time
        self.assertLessEqual(create_time, datetime.datetime.now())
        self.assertGreater(create_time, old)

    def test_heartbeat_does_not_revive_expired_token(self):
        client = Client()
        token = self.api_login(client, 'bob', 'Bob-pass-123', rid='900', uuid='u-900')
        old = datetime.datetime.now() - datetime.timedelta(seconds=EFFECTIVE_SECONDS + 1)
        RustDeskToken.objects.filter(access_token=token).update(create_time=old)
        api_post(client, '/api/heartbeat', {'id': '900', 'uuid': 'u-900'})
        self.assertEqual(RustDeskToken.objects.get(access_token=token).create_time, old)

    def test_logout_requires_token(self):
        client = Client()
        token = self.api_login(client, 'bob', 'Bob-pass-123', rid='900', uuid='u-900')
        resp = api_post(client, '/api/logout', {'id': '900', 'uuid': 'u-900'})
        self.assertIn('error', resp.json())
        self.assertTrue(RustDeskToken.objects.filter(access_token=token).exists())

        api_post(client, '/api/logout', {'id': '900', 'uuid': 'u-900'}, token=token)
        self.assertFalse(RustDeskToken.objects.filter(access_token=token).exists())

    def test_tokens_are_unique(self):
        client = Client()
        first = self.api_login(client, 'bob', 'Bob-pass-123', rid='901')
        second = self.api_login(client, 'alice', 'Alice-pass-123', rid='902')
        self.assertNotEqual(first, second)

    def test_sysinfo_updates_only_allowed_fields(self):
        client = Client()
        info = {'id': '900', 'uuid': 'u-900', 'cpu': 'c', 'hostname': 'h', 'memory': 'm', 'os': 'o', 'version': '1'}
        api_post(client, '/api/sysinfo', info)
        device = RustDeskDevice.objects.get(rid='900')
        created = device.create_time

        api_post(client, '/api/sysinfo', dict(info, hostname='h2', create_time='2000-01-01 00:00:00', unknown='x'))
        device.refresh_from_db()
        self.assertEqual(device.hostname, 'h2')
        self.assertEqual(device.create_time, created)


class DeviceStatusTests(BaseTestCase):
    def make_device(self, rid, seconds_ago):
        device = RustDeskDevice.objects.create(rid=rid, uuid=f'u-{rid}', cpu='c', hostname='h', memory='m', os='o', version='1')
        update_time = datetime.datetime.now() - datetime.timedelta(seconds=seconds_ago)
        RustDeskDevice.objects.filter(id=device.id).update(update_time=update_time)

    def test_online_status(self):
        self.make_device('111', 10)
        # Seen exactly a day ago: .seconds would be 0 and the device would look online
        self.make_device('222', 86400)
        client = self.web_client('admin', 'Admin-pass-123')
        resp = client.get('/api/work')
        self.assertEqual(resp.context['online_count_single'], 1)
        self.assertEqual(resp.context['single_info'][0]['status'], 'Online')
        self.assertEqual(resp.context['online_count_all'], 1)
        statuses = {x['rid']: x['status'] for x in resp.context['all_info']}
        self.assertEqual(statuses, {'111': 'Online', '222': 'X'})

    def test_offline_after_timeout(self):
        self.make_device('111', ONLINE_SECONDS + 1)
        client = self.web_client('admin', 'Admin-pass-123')
        self.assertEqual(client.get('/api/work').context['online_count_single'], 0)

    def test_peer_of_deleted_user_does_not_break_page(self):
        self.make_device('333', 10)
        RustDeskPeer.objects.create(uid='9999', rid='333', alias='orphan')
        client = self.web_client('admin', 'Admin-pass-123')
        resp = client.get('/api/work')
        self.assertEqual(resp.status_code, 200)
        owners = {x['rid']: x['rust_user'] for x in resp.context['all_info']}
        self.assertEqual(owners['333'], '')

    def test_regular_user_does_not_get_all_devices(self):
        self.make_device('111', 10)
        client = self.web_client('bob', 'Bob-pass-123')
        self.assertEqual(client.get('/api/work').context['all_info'], [])


class FormErrorTests(BaseTestCase):
    def test_invalid_forms_are_shown_again(self):
        bob = self.web_client('bob', 'Bob-pass-123')
        self.assertEqual(bob.post('/api/add_peer', {'clientID': '333'}).status_code, 200)
        self.assertEqual(bob.post('/api/edit_peer', {'clientID': '222'}).status_code, 200)
        self.assertEqual(bob.post('/api/edit_peer', {'clientID': '111', 'alias': 'x'}).status_code, 404)
        admin = self.web_client('admin', 'Admin-pass-123')
        self.assertEqual(admin.post('/api/assign_peer', {'clientID': '333'}).status_code, 200)

    def test_edit_peer_works_when_rid_is_shared(self):
        RustDeskPeer.objects.create(uid=self.admin.id, rid='222', alias='copy')
        bob = self.web_client('bob', 'Bob-pass-123')
        self.assertEqual(bob.get('/api/edit_peer?rid=222').status_code, 200)
        bob.post('/api/edit_peer', {'clientID': '222', 'alias': 'renamed'})
        self.assertEqual(RustDeskPeer.objects.get(uid=self.bob.id, rid='222').alias, 'renamed')
        self.assertEqual(RustDeskPeer.objects.get(uid=self.admin.id, rid='222').alias, 'copy')

    def test_user_action_without_action_shows_login(self):
        self.assertEqual(Client().get('/api/user_action').status_code, 200)


class AddressBookTests(BaseTestCase):
    def post_book(self, client, token, book):
        return api_post(client, '/api/ab', {'data': json.dumps(book)}, token=token).json()

    def test_save_and_load(self):
        client = Client()
        token = self.api_login(client, 'alice', 'Alice-pass-123')
        book = {
            'tags': ['work'],
            'tag_colors': json.dumps({'work': 123}),
            'peers': [{'id': '555', 'username': 'u', 'hostname': 'h', 'alias': 'a', 'platform': 'p', 'tags': ['work'], 'hash': ''}],
        }
        resp = self.post_book(client, token, book)
        self.assertNotIn('error', resp)
        self.assertEqual(resp['code'], 1)

        data = json.loads(client.get('/api/ab', HTTP_AUTHORIZATION=f'Bearer {token}').json()['data'])
        self.assertEqual(data['tags'], ['work'])
        self.assertEqual(json.loads(data['tag_colors']), {'work': 123})
        self.assertEqual(data['peers'][0]['id'], '555')
        self.assertEqual(data['peers'][0]['tags'], ['work'])

    def test_empty_peer_list_clears_book(self):
        client = Client()
        token = self.api_login(client, 'bob', 'Bob-pass-123')
        self.post_book(client, token, {'tags': [], 'peers': []})
        self.assertFalse(RustDeskPeer.objects.filter(uid=self.bob.id).exists())

    def test_failed_save_keeps_old_book(self):
        client = Client()
        token = self.api_login(client, 'bob', 'Bob-pass-123')
        resp = self.post_book(client, token, {'peers': [{'alias': 'no id'}]})
        self.assertIn('error', resp)
        self.assertTrue(RustDeskPeer.objects.filter(uid=self.bob.id, rid='222').exists())

    def test_invalid_tag_color_does_not_break_loading(self):
        RustDeskTag.objects.create(uid=self.bob.id, tag_name='t', tag_color='red')
        client = Client()
        token = self.api_login(client, 'bob', 'Bob-pass-123')
        resp = client.get('/api/ab', HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.json()['data'])['tags'], ['t'])


class AuditTests(BaseTestCase):
    def test_connection_log(self):
        client = Client()
        api_post(client, '/api/audit/conn', {'action': 'new', 'conn_id': 7, 'ip': '1.2.3.4', 'id': '111', 'uuid': 'u'})
        api_post(client, '/api/audit/conn', {'conn_id': 7, 'session_id': 5, 'peer': ['222', 'bob']})
        api_post(client, '/api/audit/conn', {'action': 'close', 'conn_id': 7})
        log = ConnLog.objects.get(conn_id='7')
        self.assertEqual(log.from_id, '222')
        self.assertIsNotNone(log.conn_end)

    def test_file_log(self):
        api_post(Client(), '/api/audit/file', {
            'is_file': True, 'path': '/tmp/a', 'peer_id': '222', 'id': '111', 'type': 1,
            'info': json.dumps({'ip': '1.2.3.4', 'files': [['a', 2048]]}),
        })
        log = FileLog.objects.get()
        self.assertEqual(log.filesize, '2.0 KB')

    def test_malformed_requests_do_not_fail(self):
        client = Client()
        for path, body in (('/api/audit', 'not json'), ('/api/sysinfo', '[]'), ('/api/heartbeat', '{}')):
            resp = client.post(path, body, content_type='application/json')
            self.assertEqual(resp.status_code, 400, path)
            self.assertIn('error', resp.json())

    def test_logs_pages_show_entries_without_start_time(self):
        ConnLog.objects.create(action='new', conn_id='1', rid='111')
        ConnLog.objects.create(action='new', conn_id='2', rid='222', conn_start=datetime.datetime.now())
        FileLog.objects.create(file='a', remote_id='111')
        client = self.web_client('admin', 'Admin-pass-123')
        resp = client.get('/api/conn_log')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([x.conn_id for x in resp.context['page_obj']], ['2', '1'])
        self.assertEqual(resp.context['page_obj'][1].alias, 'admin-pc')
        self.assertEqual(client.get('/api/file_log').status_code, 200)


class MiscTests(BaseTestCase):
    def test_sysinfo_creates_device(self):
        api_post(Client(), '/api/sysinfo', {'id': '777', 'uuid': 'u', 'cpu': 'Intel Core i7-8700 CPU @ 3.20GHz', 'os': 'Windows 11 Pro'})
        device = RustDeskDevice.objects.get(rid='777')
        self.assertEqual(device.os, 'Windows 11 Pro')
        self.assertEqual(device.username, '-')

    def test_urls_are_anchored(self):
        client = Client()
        for path in ('/api/abc', '/api/ab/settings', '/api/login-options', '/api/sysinfo_ver'):
            self.assertEqual(client.post(path).status_code, 404, path)

    @override_settings(RUSTDESK_KEY='my-key', RUSTDESK_CONFIG='my-config')
    def test_installers_page_uses_settings(self):
        client = self.web_client('bob', 'Bob-pass-123')
        resp = client.get('/api/installers')
        self.assertContains(resp, 'my-key')
        self.assertContains(resp, 'my-config')
        self.assertContains(resp, 'http://testserver/api/installers/install-mac.sh')
        self.assertNotContains(resp, 'UniqueURL')

    @override_settings(ID_SERVER='id.example.com', RELAY_SERVER='', RUSTDESK_KEY='KEY+/=',
                       RUSTDESK_CONFIG='', API_URL='https://api.example.com/')
    def test_config_is_generated_from_settings(self):
        client = self.web_client('bob', 'Bob-pass-123')
        config = client.get('/api/installers').context['rustdesk_config']
        decoded = json.loads(base64.b64decode(config[::-1]))
        self.assertEqual(decoded, {'host': 'id.example.com', 'relay': '', 'api': 'https://api.example.com', 'key': 'KEY+/='})

    @override_settings(ID_SERVER='', RUSTDESK_CONFIG='')
    def test_no_config_without_id_server(self):
        client = self.web_client('bob', 'Bob-pass-123')
        self.assertEqual(client.get('/api/installers').context['rustdesk_config'], '')

    @override_settings(RUSTDESK_CONFIG='abc123==', RUSTDESK_VERSION='1.4.2')
    def test_installer_scripts_are_filled_in(self):
        client = Client()
        expected = {
            'install.bat': ('set version=1.4.2', 'set rustdesk_cfg="abc123=="'),
            'install.ps1': ('$version = "1.4.2"', '$rustdesk_cfg="abc123=="'),
            'install-linux.sh': ('VERSION="1.4.2"', 'rustdesk_cfg="abc123=="'),
            'install-mac.sh': ('VERSION="1.4.2"', 'rustdesk_cfg="abc123=="'),
        }
        for name, lines in expected.items():
            resp = client.get(f'/api/installers/{name}')
            self.assertEqual(resp.status_code, 200, name)
            self.assertIn(f'filename="{name}"', resp['Content-Disposition'])
            body = resp.content.decode()
            for line in lines:
                self.assertIn(line, body.splitlines(), name)
            self.assertNotIn('secure-string', body, name)
            self.assertNotIn('1.3.9', body, name)

    @override_settings(RUSTDESK_CONFIG='x"; rm -rf /', RUSTDESK_VERSION='1; reboot')
    def test_installer_scripts_reject_unsafe_values(self):
        body = Client().get('/api/installers/install-linux.sh').content.decode()
        self.assertIn('rustdesk_cfg="secure-string"', body)
        self.assertNotIn('rm -rf', body)
        self.assertNotIn('reboot', body)

    def test_unknown_installer_script_is_not_found(self):
        for name in ('secret_config.py', '..%2Fsettings.py', 'qrcode.png'):
            self.assertEqual(Client().get(f'/api/installers/{name}').status_code, 404, name)

    def test_permissions_only_for_admins(self):
        self.assertTrue(self.admin.has_perm('api.change_rustdeskpeer'))
        self.assertFalse(self.bob.has_perm('api.change_rustdeskpeer'))
        admin = self.web_client('admin', 'Admin-pass-123')
        self.assertEqual(admin.get('/admin/api/rustdeskpeer/?q=111').status_code, 200)
