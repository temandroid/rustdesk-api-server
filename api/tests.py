import datetime
import json

from django.test import TestCase, Client

from api.models import UserProfile, RustDeskPeer, RustDeskToken, RustDesDevice, ShareLink
from api.views_front import EFFECTIVE_SECONDS, SHARELINK_EFFECTIVE_SECONDS


def api_post(client, path, data, token=None):
    headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'} if token else {}
    return client.post(path, json.dumps(data), content_type='application/json', **headers)


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
        device = RustDesDevice.objects.get(rid='900')
        created = device.create_time

        api_post(client, '/api/sysinfo', dict(info, hostname='h2', create_time='2000-01-01 00:00:00', unknown='x'))
        device.refresh_from_db()
        self.assertEqual(device.hostname, 'h2')
        self.assertEqual(device.create_time, created)
