"""rustdesk_server_api URL Configuration

https://docs.djangoproject.com/en/stable/topics/http/urls/
"""
from django.contrib import admin
from django.contrib.staticfiles.views import serve as serve_static
from django.urls import include, path, re_path

from api.views_front import index

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', index, name='index'),
    path('api/', include('api.urls')),
    # Serve static files from the app even with DEBUG off, so the server works
    # without a separate web server. A web server can serve `collectstatic` output instead.
    re_path(r'^static/(?P<path>.*)$', serve_static, {'insecure': True}),
]
