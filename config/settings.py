from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit
import os
import sys
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv()

def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name):
    return [item.strip() for item in os.getenv(name, '').split(',') if item.strip()]

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

DEBUG = env_bool('DEBUG', False)
TESTING = 'test' in sys.argv

SECRET_KEY = os.getenv('SECRET_KEY') or ("django-test-secret-key" if DEBUG else '')
if not SECRET_KEY:
    raise ImproperlyConfigured('SECRET_KEY must be set when DEBUG is False.')

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'authentication',
    'users',
    'problems',
    'uploader',
    'drf_spectacular',
]

MIDDLEWARE = [
    'config.middleware.RequestSizeLimitMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    "default": dj_database_url.parse(os.environ.get('DATABASE_URL', 'sqlite:///db.sqlite3'))
}

# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

EMAIL_BACKEND_PATH = os.getenv(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend'
    if DEBUG
    else 'django.core.mail.backends.smtp.EmailBackend',
)

if EMAIL_BACKEND_PATH == 'django.core.mail.backends.smtp.EmailBackend':
    EMAIL_OPTIONS = {
        'host': os.getenv('EMAIL_HOST', ''),
        'port': int(os.getenv('EMAIL_PORT', '587')),
        'username': os.getenv('EMAIL_HOST_USER', ''),
        'password': os.getenv('EMAIL_HOST_PASSWORD', ''),
        'use_tls': env_bool('EMAIL_USE_TLS', True),
    }
else:
    EMAIL_OPTIONS = {}

MAILERS = {
    'default': {
        'BACKEND': EMAIL_BACKEND_PATH,
        'OPTIONS': EMAIL_OPTIONS,
    },
}

SUBMISSION_MAX_FILES = 200
SUBMISSION_MAX_PATH_LENGTH = 255
SUBMISSION_MAX_TOTAL_BYTES = 1024 * 1024
SUBMISSION_MAX_PENDING_PER_USER = 2
SUBMISSION_MAX_PENDING_GLOBAL = 20
SUBMISSION_PENDING_WINDOW_SECONDS = 600

PROBLEM_MAX_FILES = 200
PROBLEM_FILE_MAX_CHARS = 256 * 1024
PROBLEM_MAX_TOTAL_CHARS = 1024 * 1024

REQUEST_MAX_BYTES = 8 * 1024 * 1024

EVALUATOR_WORKSPACE_SIZE = '128m'
EVALUATOR_TMP_SIZE = '64m'
EVALUATOR_FALLBACK_UID = 65534


# Celery
# https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html

REDIS_URL = os.getenv('REDIS_URL') or ('redis://localhost:6379/0' if DEBUG or TESTING else '')
if not REDIS_URL:
    raise ImproperlyConfigured('REDIS_URL must be set when DEBUG is False.')

if TESTING:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
else:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': REDIS_URL}}

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND') or None
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_ALWAYS_EAGER = env_bool('CELERY_TASK_ALWAYS_EAGER', False)
CELERY_TASK_EAGER_PROPAGATES = CELERY_TASK_ALWAYS_EAGER
CELERY_BEAT_SCHEDULE = {
    'cleanup-evaluator-leftovers': {
        'task': 'problems.tasks.cleanup_evaluator_leftovers',
        'schedule': 300,
    },
    'flush-expired-tokens': {
        'task': 'authentication.tasks.flush_expired_tokens',
        'schedule': 86400,
    },
}


REST_FRAMEWORK = {
    'NUM_PROXIES': int(os.getenv('NUM_PROXIES', '1')),
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'authentication.authentication.CookieJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'send-problems': '20/min',
        'send-content': '20/min',
        'send-score': '20/min',
        'submit': '10/min',
        'submit-details': '40/min',
        'upload-problem': '3/min',
        'auth-signup': '10/hour',
        'auth-login': '10/min',
        'auth-refresh': '20/min',
        'auth-social': '10/min',
        'history': '20/min',
        'comment': '20/min',
        'comments-read': '60/min',
        'like': '40/min',
        'unlike': '40/min',
        'profile': '20/min',
        'activity-track': '20/min',
        'update-problem': '10/min',
        'auth-state': '20/min',
        'updates-history': '20/min',
    },
}


SPECTACULAR_SETTINGS = {
    'SERVE_PERMISSIONS': ['rest_framework.permissions.IsAdminUser'],
}

ADMIN_URL_PATH = os.getenv('ADMIN_URL_PATH', 'admin/').strip('/') + '/'
ADMIN_LOGIN_MAX_ATTEMPTS_PER_MINUTE = 5

OAUTH_STATE_COOKIE_NAME = 'oauth_state'
OAUTH_STATE_MAX_AGE = 600

AUTH_USER_MODEL = 'users.User'

JWT_SIGNING_KEY = os.getenv('JWT_SIGNING_KEY', 'django-insecure-jwt-dev-key-do-not-use-in-production')

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=10),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=14),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': JWT_SIGNING_KEY,
}

AUTH_ACCESS_COOKIE_NAME = 'access_token'
AUTH_ACCESS_COOKIE_PATH = '/'
AUTH_REFRESH_COOKIE_NAME = 'refresh_token'
AUTH_REFRESH_COOKIE_PATH = '/api/auth/'
AUTH_COOKIE_SAMESITE = 'Lax'
AUTH_COOKIE_DOMAIN = os.getenv('AUTH_COOKIE_DOMAIN') or None
AUTH_COOKIE_SECURE = env_bool('AUTH_COOKIE_SECURE', False)

GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '')
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '')
GOOGLE_OAUTH_REDIRECT_URI = os.getenv('GOOGLE_OAUTH_REDIRECT_URI', '')

GITHUB_OAUTH_CLIENT_ID = os.getenv('GITHUB_OAUTH_CLIENT_ID', '')
GITHUB_OAUTH_CLIENT_SECRET = os.getenv('GITHUB_OAUTH_CLIENT_SECRET', '')
GITHUB_OAUTH_REDIRECT_URI = os.getenv('GITHUB_OAUTH_REDIRECT_URI', '')


CORS_ALLOWED_ORIGINS = env_list('CORS_ALLOWED_ORIGINS')
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = AUTH_COOKIE_SECURE
SESSION_COOKIE_SECURE = AUTH_COOKIE_SECURE

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', AUTH_COOKIE_SECURE)
SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', 3600 if AUTH_COOKIE_SECURE else 0))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', AUTH_COOKIE_SECURE)
SECURE_HSTS_PRELOAD = env_bool('SECURE_HSTS_PRELOAD', False)