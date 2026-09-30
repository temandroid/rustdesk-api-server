from django.urls import path, re_path

from api import views_api, views_front

urlpatterns = [
    # RustDesk client API
    path('login', views_api.login),
    path('logout', views_api.logout),
    path('ab', views_api.ab),
    path('users', views_api.users),
    path('peers', views_api.peers),
    path('currentUser', views_api.currentUser),
    path('sysinfo', views_api.sysinfo),
    path('heartbeat', views_api.heartbeat),
    # Clients post to /api/audit/conn and /api/audit/file, older ones to /api/audit
    re_path(r'^audit(?:/(?:conn|file))?$', views_api.audit),

    # Web UI
    path('user_action', views_front.user_action, name='user_action'),
    path('work', views_front.work, name='work'),
    path('share', views_front.share, name='share'),
    path('share/<str:shash>', views_front.share_accept, name='share_accept'),
    path('installers', views_front.installers, name='installers'),
    path('installers/<str:name>', views_front.installer_script, name='installer_script'),
    path('conn_log', views_front.conn_log, name='conn_log'),
    path('file_log', views_front.file_log, name='file_log'),
    path('add_peer', views_front.add_peer, name='add_peer'),
    path('delete_peer', views_front.delete_peer, name='delete_peer'),
    path('edit_peer', views_front.edit_peer, name='edit_peer'),
    path('assign_peer', views_front.assign_peer, name='assign_peer'),
]
