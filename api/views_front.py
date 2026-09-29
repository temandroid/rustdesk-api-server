import datetime
import json
import os
import secrets

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.forms.models import model_to_dict
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from api.models import RustDeskPeer, RustDeskDevice, UserProfile, ShareLink, ConnLog, FileLog
from .forms import AddPeerForm, EditPeerForm, AssignPeerForm

# Lifetime of a client access token without heartbeats
EFFECTIVE_SECONDS = 7200
SHARELINK_EFFECTIVE_SECONDS = 15 * 60
# A device is shown as online if it sent a heartbeat within this period
ONLINE_SECONDS = 120
LOG_PAGE_SIZE = 20

# Pages available only to administrators (is_admin)
admin_required = user_passes_test(lambda u: u.is_authenticated and u.is_admin)


def is_online(device, now):
    return (now - device.update_time).total_seconds() <= ONLINE_SECONDS


def online_first(items):
    # Stable sort: online entries first, original order otherwise
    return sorted(items, key=lambda item: item['status'] == 'Online', reverse=True)


def index(request):
    if request.user.is_authenticated:
        return redirect('work')
    return redirect(settings.LOGIN_URL)


def user_action(request):
    action = request.GET.get('action', '')
    if action == 'logout':
        return user_logout(request)
    if action == 'login' or request.method == 'GET':
        return user_login(request)
    return HttpResponseNotAllowed(['GET'])


def user_login(request):
    # Handles user login
    if request.method == 'GET':
        return render(request, 'login.html')

    username = request.POST.get('account', '')
    password = request.POST.get('password', '')
    if not username or not password:
        return JsonResponse({'code':0, 'msg':'There was a problem.'})

    user = auth.authenticate(username=username,password=password)
    if user:
        auth.login(request, user)
        return JsonResponse({'code':1, 'url':reverse('work')})
    else:
        return JsonResponse({'code':0, 'msg':'Account or password incorrect!'})


@login_required
def user_logout(request):
    # Handles user logout
    auth.logout(request)
    return redirect(settings.LOGIN_URL)


def get_single_info(uid):
    # Peers from the user's address book with the latest device information
    online_count = 0
    peers = list(RustDeskPeer.objects.filter(Q(uid=uid)))
    devices = {x.rid:x for x in RustDeskDevice.objects.filter(rid__in=[p.rid for p in peers])}

    now = datetime.datetime.now()
    result = []
    for peer in peers:
        info = model_to_dict(peer)
        info['has_rhash'] = 'Yes' if len(peer.rhash)>1 else 'No'
        info['status'] = 'X'
        device = devices.get(peer.rid)
        if device:
            info['create_time'] = device.create_time.strftime('%Y-%m-%d')
            info['update_time'] = device.update_time.strftime('%Y-%m-%d %H:%M')
            info['version'] = device.version
            info['memory'] = device.memory
            info['cpu'] = device.cpu
            info['os'] = device.os
            info['ip'] = device.ip
            if is_online(device, now):
                info['status'] = 'Online'
                online_count += 1
        result.append(info)

    return (online_first(result), online_count)


def get_all_info():
    # All devices known to the server, with the users whose address books contain them
    online_count = 0
    usernames = {str(uid): username for uid, username in UserProfile.objects.values_list('id', 'username')}
    owners = {}
    for rid, uid in RustDeskPeer.objects.values_list('rid', 'uid'):
        if uid in usernames:
            owners[rid] = usernames[uid]

    now = datetime.datetime.now()
    result = []
    for device in RustDeskDevice.objects.all():
        online = is_online(device, now)
        online_count += online
        result.append({
            'rid': device.rid,
            'rust_user': owners.get(device.rid, ''),
            'version': device.version,
            'username': device.username,
            'hostname': device.hostname,
            'os': device.os,
            'cpu': device.cpu,
            'memory': device.memory,
            'create_time': device.create_time.strftime('%Y-%m-%d'),
            'update_time': device.update_time.strftime('%Y-%m-%d %H:%M'),
            'status': 'Online' if online else 'X',
            'ip': device.ip,
        })
    return (online_first(result), online_count)


@login_required
def work(request):
    # Main work view
    single_info, online_count_single = get_single_info(request.user.id)
    all_info, online_count_all = get_all_info() if request.user.is_admin else ([], 0)
    return render(request, 'show_work.html', {'single_info':single_info, 'all_info':all_info, 'u':request.user, 'online_count_single':online_count_single, 'online_count_all':online_count_all})


def check_sharelink_expired(sharelink):
    # Checks if a share link is expired
    if sharelink.is_expired:
        return True
    age = datetime.datetime.now() - sharelink.create_time
    if age.total_seconds() < SHARELINK_EFFECTIVE_SECONDS:
        return False
    sharelink.is_expired = True
    sharelink.save()
    return True


@login_required
def share(request):
    # Share view: lists the user's machines and active links, creates new links
    if request.method == 'POST':
        try:
            data = json.loads(request.POST.get('data', '[]'))
            rustdesk_ids = [x['title'].split('|')[0] for x in data]
        except (ValueError, TypeError, KeyError, AttributeError):
            return JsonResponse({'code':0, 'msg':'Invalid data.'})
        if not rustdesk_ids:
            return JsonResponse({'code':0, 'msg':'Data is empty.'})
        sharelink = ShareLink.objects.create(
            uid=request.user.id,
            shash=secrets.token_urlsafe(32),
            peers=','.join(rustdesk_ids),
        )
        return JsonResponse({'code':1, 'shash':sharelink.shash})

    # Handle expiry on request instead of running a cron job
    active = Q(uid=request.user.id) & Q(is_used=False) & Q(is_expired=False)
    for sl in ShareLink.objects.filter(active):
        check_sharelink_expired(sl)
    peers = [{'id':ix+1, 'name':f'{p.rid}|{p.alias}'} for ix, p in enumerate(RustDeskPeer.objects.filter(Q(uid=request.user.id)))]
    sharelinks = ShareLink.objects.filter(active)
    return render(request, 'share.html', {'peers':peers, 'sharelinks':sharelinks})


@login_required
def share_accept(request, shash):
    # Accepting a share link changes data, so GET only shows a confirmation form
    url = request.build_absolute_uri()
    if request.method == 'GET':
        return render(request, 'share_accept.html', {'url':url})

    expired_msg = f'Link {url}:\nThe share link does not exist or has expired.'
    sharelink = ShareLink.objects.filter(Q(shash=shash) & Q(is_used=False) & Q(is_expired=False)).first()
    if not sharelink or check_sharelink_expired(sharelink):
        return render(request, 'msg.html', {'title':'Error', 'msg':expired_msg})
    if str(request.user.id) == str(sharelink.uid):
        msg = f'Link {url}:\n\nYou can not share the link with yourself, can you ! '
        return render(request, 'msg.html', {'title':'Error', 'msg':msg})

    # Mark as used atomically so the link can be redeemed only once
    claimed = ShareLink.objects.filter(Q(id=sharelink.id) & Q(is_used=False)).update(is_used=True)
    if not claimed:
        return render(request, 'msg.html', {'title':'Error', 'msg':expired_msg})

    # Skip peers already in the recipient's address book
    peers_self_ids = set(RustDeskPeer.objects.filter(Q(uid=request.user.id)).values_list('rid', flat=True))
    peers_share = RustDeskPeer.objects.filter(Q(rid__in=sharelink.peers.split(',')) & Q(uid=sharelink.uid))
    msg = ''
    copied = set()
    for peer in peers_share:
        if peer.rid in peers_self_ids or peer.rid in copied:
            continue
        peer.id = None
        peer.uid = request.user.id
        peer.save()
        copied.add(peer.rid)
        msg += f"{peer.rid},"
    msg += 'has been successfully acquired.'
    return render(request, 'msg.html', {'title':'Success', 'msg':msg})


@login_required
def installers(request):
    configs_dir = os.path.join(settings.BASE_DIR, 'static', 'configs')
    exe_name = f'rustdesk-licensed-{settings.RUSTDESK_CONFIG}.exe' if settings.RUSTDESK_CONFIG else ''
    if exe_name and not os.path.exists(os.path.join(configs_dir, exe_name)):
        exe_name = ''
    return render(request, 'installers.html', {
        'api_url': request.build_absolute_uri('/').rstrip('/'),
        'rustdesk_key': settings.RUSTDESK_KEY,
        'rustdesk_config': settings.RUSTDESK_CONFIG,
        'exe_name': exe_name,
        'has_qrcode': os.path.exists(os.path.join(configs_dir, 'qrcode.png')),
    })


def format_duration(start, end):
    if not start or not end:
        return '-'
    m, s = divmod(round((end - start).total_seconds()), 60)
    h, m = divmod(m, 60)
    return f'{h:02d}:{m:02d}:{s:02d}'


def peer_aliases(rids):
    return dict(RustDeskPeer.objects.filter(rid__in=set(rids)).values_list('rid', 'alias'))


def get_page(request, queryset):
    return Paginator(queryset, LOG_PAGE_SIZE).get_page(request.GET.get('page'))


@admin_required
def conn_log(request):
    page_obj = get_page(request, ConnLog.objects.order_by(F('conn_start').desc(nulls_last=True), '-id'))
    aliases = peer_aliases([x.rid for x in page_obj] + [x.from_id for x in page_obj])
    for log in page_obj:
        log.alias = aliases.get(log.rid, 'UNKNOWN')
        log.from_alias = aliases.get(log.from_id, 'UNKNOWN')
        log.duration = format_duration(log.conn_start, log.conn_end)
    return render(request, 'show_conn_log.html', {'page_obj':page_obj})


@admin_required
def file_log(request):
    page_obj = get_page(request, FileLog.objects.order_by(F('logged_at').desc(nulls_last=True), '-id'))
    aliases = peer_aliases([x.remote_id for x in page_obj] + [x.user_id for x in page_obj])
    for log in page_obj:
        log.remote_alias = aliases.get(log.remote_id, 'UNKNOWN')
        log.user_alias = aliases.get(log.user_id, 'UNKNOWN')
    return render(request, 'show_file_log.html', {'page_obj':page_obj})


def peer_from_form(form, uid):
    data = form.cleaned_data
    return RustDeskPeer(
        uid=uid,
        rid=data['clientID'],
        username=data['username'],
        hostname=data['hostname'],
        platform=data['platform'],
        alias=data['alias'],
        tags=data['tags'],
        ip=data['ip'],
    )


@login_required
def add_peer(request):
    rid = request.GET.get('rid') or request.POST.get('clientID', '')
    if request.method == 'POST':
        form = AddPeerForm(request.POST)
        if form.is_valid():
            peer_from_form(form, request.user.id).save()
            return redirect('work')
    else:
        form = AddPeerForm()
    return render(request, 'add_peer.html', {'form': form, 'rid': rid})


@login_required
def edit_peer(request):
    rid = request.POST.get('clientID', '') if request.method == 'POST' else request.GET.get('rid', '')
    peer = RustDeskPeer.objects.filter(Q(rid=rid) & Q(uid=request.user.id)).first()
    if not peer:
        raise Http404('Peer not found')

    if request.method == 'POST':
        form = EditPeerForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            peer.username = data['username']
            peer.hostname = data['hostname']
            peer.platform = data['platform']
            peer.alias = data['alias']
            peer.tags = data['tags']
            peer.save()
            return redirect('work')
    else:
        form = EditPeerForm(initial={
            'clientID': rid,
            'alias': peer.alias,
            'tags': peer.tags,
            'username': peer.username,
            'hostname': peer.hostname,
            'platform': peer.platform,
            'ip': peer.ip
        })
    return render(request, 'edit_peer.html', {'form': form, 'peer': peer})


@admin_required
def assign_peer(request):
    rid = request.GET.get('rid') or request.POST.get('clientID', '')
    if request.method == 'POST':
        form = AssignPeerForm(request.POST)
        if form.is_valid():
            peer_from_form(form, form.cleaned_data['uid'].id).save()
            return redirect('work')
    else:
        form = AssignPeerForm()
    return render(request, 'assign_peer.html', {'form':form, 'rid': rid})


@login_required
def delete_peer(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    rid = request.POST.get('rid')
    RustDeskPeer.objects.filter(Q(uid=request.user.id) & Q(rid=rid)).delete()
    return redirect('work')
