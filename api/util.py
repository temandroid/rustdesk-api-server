import base64
import json

from django.conf import settings as _settings


def settings(request):
    """
    Template context processor: current user and server settings used by the templates.
    """
    context = {'domain': _settings.ID_SERVER}
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        context['u'] = user
    return context


def api_url(request):
    """Public address of this API server for clients."""
    return (_settings.API_URL or request.build_absolute_uri('/')).rstrip('/')


def server_config(request):
    """
    Server configuration string for `rustdesk --config` and the client's
    "Import server config": reversed base64 of the server settings JSON, the
    format the RustDesk client exports. RUSTDESK_CONFIG overrides it.
    """
    if _settings.RUSTDESK_CONFIG:
        return _settings.RUSTDESK_CONFIG
    if not _settings.ID_SERVER:
        return ''
    config = {
        'host': _settings.ID_SERVER,
        'relay': _settings.RELAY_SERVER,
        'api': api_url(request),
        'key': _settings.RUSTDESK_KEY,
    }
    encoded = base64.b64encode(json.dumps(config, separators=(',', ':')).encode()).decode()
    return encoded[::-1]
