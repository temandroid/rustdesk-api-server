"""
Django settings for rustdesk_server_api project.

Secrets and deployment options are read from environment variables. For
compatibility, values may also be defined in rustdesk_server_api/secret_config.py;
environment variables take precedence.

For the full list of settings and their values, see
https://docs.djangoproject.com/en/stable/ref/settings/
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

try:
    from . import secret_config
except ImportError:
    secret_config = None


def get_setting(name, default=None):
    # Environment variable first, then secret_config.py, then the default
    if name in os.environ:
        return os.environ[name]
    return getattr(secret_config, name, default)


def get_list(name, default):
    value = get_setting(name, default)
    if isinstance(value, str):
        value = value.split(',')
    return [item.strip() for item in value if item.strip()]


def get_bool(name, default=False):
    value = get_setting(name, default)
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = get_setting('SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured(
        'SECRET_KEY is not set. Set the SECRET_KEY environment variable '
        'or define it in rustdesk_server_api/secret_config.py.'
    )

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = get_bool('DEBUG')
ALLOWED_HOSTS = get_list('ALLOWED_HOSTS', '*')
CSRF_TRUSTED_ORIGINS = get_list('CSRF_TRUSTED_ORIGINS', '')
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
# Behind a reverse proxy that terminates HTTPS (e.g. Nginx Proxy Manager):
# trust its X-Forwarded-Proto header so generated links use https
if get_bool('BEHIND_PROXY'):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ID server address or domain (usually the same host as the relay server)
ID_SERVER = get_setting('ID_SERVER', '')
# Public key of the ID server, shown on the installers page
RUSTDESK_KEY = get_setting('RUSTDESK_KEY', '')
# Server configuration string exported from the RustDesk client, shown on the installers page
RUSTDESK_CONFIG = get_setting('RUSTDESK_CONFIG', '')

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
AUTH_USER_MODEL = 'api.UserProfile'
LOGIN_URL = '/api/user_action?action=login'

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'rustdesk_server_api.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'api.util.settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'rustdesk_server_api.wsgi.application'


# Database
# https://docs.djangoproject.com/en/stable/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': get_setting('DB_PATH', BASE_DIR / 'db' / 'db.sqlite3'),
    }
}


# Password validation
# https://docs.djangoproject.com/en/stable/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/stable/topics/i18n/

LANGUAGE_CODE = 'en-us'
# Times are stored as naive datetimes in this time zone (USE_TZ is off because
# existing databases contain naive values).
TIME_ZONE = get_setting('TIME_ZONE', 'UTC')
USE_I18N = True
USE_TZ = False


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/stable/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
# Target of `manage.py collectstatic`, for serving static files with a web server
STATIC_ROOT = BASE_DIR / 'static_root'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'loggers': {
        'api': {'handlers': ['console'], 'level': get_setting('LOG_LEVEL', 'INFO')},
    },
}
