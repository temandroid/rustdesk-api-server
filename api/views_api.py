# cython:language_level=3
from django.http import JsonResponse
import json
import time
import datetime
import hashlib
import math
import secrets
from django.views.decorators.csrf import csrf_exempt
from django.contrib import auth
from django.forms.models import model_to_dict
from api.models import RustDeskToken, UserProfile, RustDeskTag, RustDeskPeer, RustDesDevice, ConnLog, FileLog
from django.db.models import Q
import copy
from .views_front import *
from django.conf import settings

# Fields a client may set on RustDesDevice via /api/sysinfo
SYSINFO_FIELDS = ('cpu', 'hostname', 'memory', 'os', 'username', 'version')


def token_expired(token):
    age = datetime.datetime.now() - token.create_time
    return age.total_seconds() >= EFFECTIVE_SECONDS


def get_valid_token(request):
    # Returns the RustDeskToken from the Authorization header, or None if missing or expired
    access_token = request.META.get('HTTP_AUTHORIZATION', '')
    access_token = access_token.split('Bearer ')[-1].strip()
    if not access_token:
        return None
    token = RustDeskToken.objects.filter(Q(access_token=access_token)).first()
    if token and token_expired(token):
        token.delete()
        return None
    return token


@csrf_exempt
def login(request):
    result = {}
    if request.method == 'GET':
        result['error'] = 'Wrong request method! Please use POST.'
        return JsonResponse(result)

    data = json.loads(request.body.decode())
    
    username = data.get('username', '')
    password = data.get('password', '')
    rid = data.get('id', '')
    uuid = data.get('uuid', '')
    autoLogin = data.get('autoLogin', True)
    rtype = data.get('type', '')
    deviceInfo = data.get('deviceInfo', '')
    user = auth.authenticate(username=username, password=password)
    if not user:
        result['error'] = 'Incorrect account or password! Please try again, multiple failed attempts will lock your IP!'
        return JsonResponse(result)
    user.rid = rid
    user.uuid = uuid
    user.autoLogin = autoLogin
    user.rtype = rtype
    user.deviceInfo = json.dumps(deviceInfo)
    user.save()
    
    token = RustDeskToken.objects.filter(Q(uid=user.id) & Q(username=user.username) & Q(rid=user.rid)).first()
    
    # Check if expired
    if token and token_expired(token):
        token.delete()
        token = None
    
    if not token:
        # Get and save token
        token = RustDeskToken(
            username=user.username,
            uid=user.id,
            uuid=user.uuid,
            rid=user.rid,
            access_token=secrets.token_urlsafe(32)
        )
        token.save()

    result['access_token'] = token.access_token
    result['type'] = 'access_token'
    result['user'] = {'name': user.username}
    return JsonResponse(result)


@csrf_exempt
def logout(request):
    if request.method == 'GET':
        result = {'error':'Wrong request method!'}
        return JsonResponse(result)
    
    token = get_valid_token(request)
    if not token:
        result = {'error':'Abnormal request!'}
        return JsonResponse(result)
    token.delete()

    result = {'code':1}
    return JsonResponse(result)


@csrf_exempt
def currentUser(request):
    result = {}
    if request.method == 'GET':
        result['error'] = 'Incorrect submission method!'
        return JsonResponse(result)
    token = get_valid_token(request)
    user = None
    if token:
        user = UserProfile.objects.filter(Q(id=token.uid)).first()
    
    if user:
        if token:
            result['access_token'] = token.access_token
        result['type'] = 'access_token'
        result['name'] = user.username
    return JsonResponse(result)


@csrf_exempt
def ab(request):
    '''
    '''
    token = get_valid_token(request)
    if not token:
        result = {'error':'Error pulling the list!'}
        return JsonResponse(result)
    
    if request.method == 'GET':
        result = {}
        uid = token.uid
        tags = RustDeskTag.objects.filter(Q(uid=uid))
        tag_names = []
        tag_colors = {}
        if tags:
            tag_names = [str(x.tag_name) for x in tags]
            tag_colors = {str(x.tag_name):int(x.tag_color) for x in tags if x.tag_color!=''}
        
        peers_result = []
        peers = RustDeskPeer.objects.filter(Q(uid=uid))
        if peers:
            for peer in peers:
                tmp = {
                    'id': peer.rid,
                    'username': peer.username,
                    'hostname': peer.hostname,
                    'alias': peer.alias,
                    'platform': peer.platform,
                    'tags': peer.tags.split(','),
                    'hash': peer.rhash,
                }
                peers_result.append(tmp)
        
        result['updated_at'] = datetime.datetime.now()
        result['data'] = {
            'tags': tag_names,
            'peers': peers_result,
            'tag_colors': json.dumps(tag_colors)
        }
        result['data'] = json.dumps(result['data'])
        return JsonResponse(result)
    else:
        postdata = json.loads(request.body.decode())
        data = postdata.get('data', '')
        data = {} if data == '' else json.loads(data)
        tagnames = data.get('tags', [])
        tag_colors = data.get('tag_colors', '')
        tag_colors = {} if tag_colors == '' else json.loads(tag_colors)
        peers = data.get('peers', [])
        
        if tagnames:
            # Delete old tags
            RustDeskTag.objects.filter(uid=token.uid).delete()
            # Add new ones
            newlist = []
            for name in tagnames:
                tag = RustDeskTag(
                    uid=token.uid,
                    tag_name=name,
                    tag_color=tag_colors.get(name, '')
                )
                newlist.append(tag)
            RustDeskTag.objects.bulk_create(newlist)
        if peers:
            RustDeskPeer.objects.filter(uid=token.uid).delete()
            newlist = []
            for one in peers:
                peer = RustDeskPeer(
                    uid=token.uid,
                    rid=one['id'],
                    username=one['username'],
                    hostname=one['hostname'],
                    alias=one['alias'],
                    platform=one['platform'],
                    tags=','.join(one['tags']),
                    rhash=one['hash'],                  
                )
                newlist.append(peer)
            RustDeskPeer.objects.bulk_create(newlist)

    result = {
    'code':102,
    'data':'Error updating the address book'
    }
    return JsonResponse(result)

@csrf_exempt
def sysinfo(request):
    # Device information is sent only after client registration
    result = {}
    if request.method == 'GET':
        result['error'] = 'Incorrect submission method!'
        return JsonResponse(result)
    
    client_ip = get_client_ip(request)
    postdata = json.loads(request.body)
    device = RustDesDevice.objects.filter(Q(rid=postdata['id']) & Q(uuid=postdata['uuid'])).first()
    if not device:
        device = RustDesDevice(
            rid=postdata['id'],
            cpu=postdata['cpu'],
            hostname=postdata['hostname'],
            memory=postdata['memory'],
            os=postdata['os'],
            username=postdata.get('username', '-'),
            uuid=postdata['uuid'],
            version=postdata['version'],
            ip=client_ip,
        )
        device.save()
    else:
        for field in SYSINFO_FIELDS:
            if field in postdata:
                setattr(device, field, postdata[field])
        device.ip = client_ip
        device.save()
    result['data'] = 'ok'
    return JsonResponse(result)

@csrf_exempt
def heartbeat(request):
    postdata = json.loads(request.body)
    device = RustDesDevice.objects.filter(Q(rid=postdata['id']) & Q(uuid=postdata['uuid'])).first()
    if device:
        device.save()
    # Token keep-alive: extend only tokens that have not expired yet
    now = datetime.datetime.now()
    RustDeskToken.objects.filter(
        Q(rid=postdata['id']) & Q(uuid=postdata['uuid'])
        & Q(create_time__gt=now - datetime.timedelta(seconds=EFFECTIVE_SECONDS))
    ).update(create_time=now)
    result = {}
    result['data'] = 'Online'
    return JsonResponse(result)

@csrf_exempt
def audit(request):
    postdata = json.loads(request.body)
    #print(postdata)
    audit_type = postdata['action'] if 'action' in postdata else ''
    if audit_type == 'new':
        new_conn_log = ConnLog(
            action=postdata['action'] if 'action' in postdata else '',
            conn_id=postdata['conn_id'] if 'conn_id' in postdata else 0,
            from_ip=postdata['ip'] if 'ip' in postdata else '',
            from_id='',
            rid=postdata['id'] if 'id' in postdata else '',
            conn_start=datetime.datetime.now(),
            session_id=postdata['session_id'] if 'session_id' in postdata else 0,
            uuid=postdata['uuid'] if 'uuid' in postdata else '',
        )
        new_conn_log.save()
    elif audit_type =="close":
        ConnLog.objects.filter(Q(conn_id=postdata['conn_id'])).update(conn_end=datetime.datetime.now())
    elif 'is_file' in postdata:
        print(postdata)
        files = json.loads(postdata['info'])['files']
        filesize = convert_filesize(int(files[0][1]))
        new_file_log = FileLog(
            file=postdata['path'],
            user_id=postdata['peer_id'],
            user_ip=json.loads(postdata['info'])['ip'],
            remote_id=postdata['id'],
            filesize=filesize,
            direction=postdata['type'],
            logged_at=datetime.datetime.now(),
        )
        new_file_log.save()
    else:
        try:
            peer = postdata['peer']
            ConnLog.objects.filter(Q(conn_id=postdata['conn_id'])).update(session_id=postdata['session_id'])
            ConnLog.objects.filter(Q(conn_id=postdata['conn_id'])).update(from_id=peer[0])
        except:
            print(postdata)

    result = {
    'code':1,
    'data':'ok'
    }
    return JsonResponse(result)

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def convert_filesize(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])
    
@csrf_exempt
def users(request):
    result = {
    'code':1,
    'data':'Alright'
    }
    return JsonResponse(result)
    
@csrf_exempt
def peers(request):
    result = {
    'code':1,
    'data':'ok'
    }
    return JsonResponse(result)
