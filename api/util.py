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
