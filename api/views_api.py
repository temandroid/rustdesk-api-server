import datetime
import functools
import json
import logging
import math
import secrets

from django.contrib import auth
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.models import RustDeskToken, UserProfile, RustDeskTag, RustDeskPeer, RustDeskDevice, ConnLog, FileLog
from .views_front import EFFECTIVE_SECONDS

logger = logging.getLogger(__name__)

# Fields a client may set on RustDeskDevice via /api/sysinfo
SYSINFO_FIELDS = ('cpu', 'hostname', 'memory', 'os', 'username', 'version')


def client_api(view):
    # RustDesk client endpoint: no CSRF, JSON body parsed into `data`,
    # malformed requests answered with an error instead of a server error
    @csrf_exempt
    @functools.wraps(view)
    def wrapper(request):
        data = {}
        if request.method == 'POST':
            try:
                data = json.loads(request.body or b'{}')
            except ValueError:
                return JsonResponse({'error': 'Invalid JSON body!'}, status=400)
            if not isinstance(data, dict):
                return JsonResponse({'error': 'Invalid JSON body!'}, status=400)
        try:
            return view(request, data)
        except (KeyError, TypeError, ValueError, IndexError, AttributeError) as e:
            logger.warning('%s: bad request: %r', view.__name__, e)
            return JsonResponse({'error': 'Invalid request!'}, status=400)
    return wrapper


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


@client_api
def login(request, data):
    result = {}
    if request.method == 'GET':
        result['error'] = 'Wrong request method! Please use POST.'
        return JsonResponse(result)

    username = data.get('username', '')
    password = data.get('password', '')
    user = auth.authenticate(username=username, password=password)
    if not user:
        result['error'] = 'Incorrect account or password! Please try again, multiple failed attempts will lock your IP!'
        return JsonResponse(result)
    user.rid = data.get('id', '')
    user.uuid = data.get('uuid', '')
    user.autoLogin = data.get('autoLogin', True)
    user.rtype = data.get('type', '')
    user.deviceInfo = json.dumps(data.get('deviceInfo', ''))
    user.save()

    token = RustDeskToken.objects.filter(Q(uid=user.id) & Q(username=user.username) & Q(rid=user.rid)).first()

    # Check if expired
    if token and token_expired(token):
        token.delete()
        token = None

    if not token:
        token = RustDeskToken.objects.create(
            username=user.username,
            uid=user.id,
            uuid=user.uuid,
            rid=user.rid,
            access_token=secrets.token_urlsafe(32)
        )

    result['access_token'] = token.access_token
    result['type'] = 'access_token'
    result['user'] = {'name': user.username}
    return JsonResponse(result)


@client_api
def logout(request, data):
    if request.method == 'GET':
        return JsonResponse({'error':'Wrong request method!'})

    token = get_valid_token(request)
    if not token:
        return JsonResponse({'error':'Abnormal request!'})
    token.delete()
    return JsonResponse({'code':1})


@client_api
def currentUser(request, data):
    result = {}
    if request.method == 'GET':
        result['error'] = 'Incorrect submission method!'
        return JsonResponse(result)
    token = get_valid_token(request)
    user = UserProfile.objects.filter(Q(id=token.uid)).first() if token else None
    if user:
        result['access_token'] = token.access_token
        result['type'] = 'access_token'
        result['name'] = user.username
    return JsonResponse(result)


def parse_tag_color(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@client_api
def ab(request, data):
    '''Legacy address book: GET returns it, POST replaces it'''
    token = get_valid_token(request)
    if not token:
        return JsonResponse({'error':'Error pulling the list!'})

    if request.method == 'GET':
        tags = RustDeskTag.objects.filter(Q(uid=token.uid))
        tag_names = [str(x.tag_name) for x in tags]
        tag_colors = {}
        for x in tags:
            color = parse_tag_color(x.tag_color)
            if color is not None:
                tag_colors[str(x.tag_name)] = color

        peers_result = []
        for peer in RustDeskPeer.objects.filter(Q(uid=token.uid)):
            peers_result.append({
                'id': peer.rid,
                'username': peer.username,
                'hostname': peer.hostname,
                'alias': peer.alias,
                'platform': peer.platform,
                'tags': [x for x in peer.tags.split(',') if x],
                'hash': peer.rhash,
            })

        book = {
            'tags': tag_names,
            'peers': peers_result,
            'tag_colors': json.dumps(tag_colors)
        }
        return JsonResponse({'updated_at': datetime.datetime.now(), 'data': json.dumps(book)})

    book = data.get('data', '')
    book = json.loads(book) if book else {}
    tag_colors = book.get('tag_colors', '')
    tag_colors = json.loads(tag_colors) if tag_colors else {}

    # Replace the stored lists present in the request; an empty list clears them
    with transaction.atomic():
        if 'tags' in book:
            RustDeskTag.objects.filter(uid=token.uid).delete()
            RustDeskTag.objects.bulk_create([
                RustDeskTag(uid=token.uid, tag_name=name, tag_color=tag_colors.get(name, ''))
                for name in book['tags']
            ])
        if 'peers' in book:
            RustDeskPeer.objects.filter(uid=token.uid).delete()
            RustDeskPeer.objects.bulk_create([
                RustDeskPeer(
                    uid=token.uid,
                    rid=one['id'],
                    username=one.get('username', ''),
                    hostname=one.get('hostname', ''),
                    alias=one.get('alias', ''),
                    platform=one.get('platform', ''),
                    tags=','.join(str(x) for x in one.get('tags', [])),
                    rhash=one.get('hash', ''),
                )
                for one in book['peers']
            ])

    return JsonResponse({'code':1, 'data':'ok'})


@client_api
def sysinfo(request, data):
    # Device information is sent by every client with the API server configured
    if request.method == 'GET':
        return JsonResponse({'error':'Incorrect submission method!'})

    device = RustDeskDevice.objects.filter(Q(rid=data['id']) & Q(uuid=data['uuid'])).first()
    if not device:
        device = RustDeskDevice(rid=data['id'], uuid=data['uuid'], username='-')
    for field in SYSINFO_FIELDS:
        if field in data:
            setattr(device, field, data[field])
    device.ip = get_client_ip(request)
    device.save()
    return JsonResponse({'data':'ok'})


@client_api
def heartbeat(request, data):
    device = RustDeskDevice.objects.filter(Q(rid=data['id']) & Q(uuid=data['uuid'])).first()
    if device:
        device.save()
    # Token keep-alive: extend only tokens that have not expired yet
    now = datetime.datetime.now()
    RustDeskToken.objects.filter(
        Q(rid=data['id']) & Q(uuid=data['uuid'])
        & Q(create_time__gt=now - datetime.timedelta(seconds=EFFECTIVE_SECONDS))
    ).update(create_time=now)
    return JsonResponse({'data':'Online'})


@client_api
def audit(request, data):
    audit_type = data.get('action', '')
    if audit_type == 'new':
        ConnLog.objects.create(
            action=audit_type,
            conn_id=data.get('conn_id', 0),
            from_ip=data.get('ip', ''),
            from_id='',
            rid=data.get('id', ''),
            conn_start=datetime.datetime.now(),
            session_id=data.get('session_id', 0),
            uuid=data.get('uuid', ''),
        )
    elif audit_type == 'close':
        ConnLog.objects.filter(Q(conn_id=data['conn_id'])).update(conn_end=datetime.datetime.now())
    elif 'is_file' in data:
        info = json.loads(data['info'])
        files = info.get('files') or [[None, 0]]
        FileLog.objects.create(
            file=data['path'],
            user_id=data['peer_id'],
            user_ip=info.get('ip', ''),
            remote_id=data['id'],
            filesize=convert_filesize(int(files[0][1])),
            direction=data['type'],
            logged_at=datetime.datetime.now(),
        )
    elif 'peer' in data and 'conn_id' in data:
        ConnLog.objects.filter(Q(conn_id=data['conn_id'])).update(
            session_id=data.get('session_id', 0),
            from_id=data['peer'][0],
        )
    else:
        logger.info('audit: unhandled event %s', data)

    return JsonResponse({'code':1, 'data':'ok'})


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def convert_filesize(size_bytes):
    if size_bytes <= 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = min(int(math.floor(math.log(size_bytes, 1024))), len(size_name) - 1)
    s = round(size_bytes / math.pow(1024, i), 2)
    return "%s %s" % (s, size_name[i])


@client_api
def users(request, data):
    return JsonResponse({'code':1, 'data':'Alright'})


@client_api
def peers(request, data):
    return JsonResponse({'code':1, 'data':'ok'})
