"""
Django settings for mysite project.

Generated by 'django-admin startproject' using Django 1.10.1.

For more information on this file, see
https://docs.djangoproject.com/en/1.10/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.10/ref/settings/
"""

import os
import braintree
from datetime import datetime
from django.core.exceptions import ImproperlyConfigured
import logging
import pytz
from logging.handlers import SysLogHandler
from logdna import LogDNAHandler

ENV_DEV = 'dev'
ENV_STAGE = 'stage'
ENV_PROD = 'prod'

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.10/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 's*l=k=*e@(jj2t6hk1er_g!6g5ztxp+n@90+@a1$nqn*(7mw(d'

def get_environment_variable(var_name):
    """Attempt to get key from os.environ, or raise ImproperlyConfigured exception"""
    try:
        return os.environ[var_name]
    except KeyError:
        raise ImproperlyConfigured('The {0} environment variable is not set'.format(var_name))


ENV_TYPE = get_environment_variable('ORBIT_ENV_TYPE')
if not ENV_TYPE in (ENV_DEV, ENV_PROD, ENV_STAGE):
    raise ImproperlyConfigured('Invalid value for ORBIT_ENV_TYPE.')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True if ENV_TYPE == ENV_DEV else False

ADMINS = [
    ('Faria Chowdhury',     'faria.chowdhury@gmail.com'),
#    ('Max Hwang',           'mch@codeabovelab.com'),
#    ('Gleb Starodubstev',   'gleb@codeabovelab.com')
]

# Note: This value should match the X_FORWARDED_HOST in the nginx conf file.
SERVER_HOSTNAME = get_environment_variable('ORBIT_SERVER_HOSTNAME')  # e.g. test1.orbitcme.com
SERVER_IP = os.environ.get('ORBIT_SERVER_IP_ADDR', '')
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]', SERVER_HOSTNAME]
if SERVER_IP:
    ALLOWED_HOSTS.append(SERVER_IP)

# This value used by various expiration-related settings
APP_EXPIRE_SECONDS = 86400*60  # 60 days

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'oauth2_provider',
    'rest_framework',
    'storages',
    'users.apps.UsersConfig',
    'rest_framework_swagger',
    'pagedown',
    'django_extensions',
]

# Session
SESSION_COOKIE_AGE = APP_EXPIRE_SECONDS
SESSION_COOKIE_SECURE = False if ENV_TYPE == ENV_DEV else True # stage/prod must use https

# django-storages AWS S3
AWS_ACCESS_KEY_ID = get_environment_variable('ORBIT_AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = get_environment_variable('ORBIT_AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = get_environment_variable('ORBIT_AWS_S3_BUCKET_NAME')
AWS_QUERYSTRING_AUTH = True
AWS_QUERYSTRING_EXPIRE = APP_EXPIRE_SECONDS
AWS_DEFAULT_ACL = 'private'
AWS_S3_ENCRYPTION = True
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
FEED_MEDIA_BASEDIR = 'entries'
CERTIFICATE_MEDIA_BASEDIR = 'certificates'
MEDIA_URL = "http://%s.s3.amazonaws.com/" % AWS_STORAGE_BUCKET_NAME

# File Upload settings
# The maximum size (in bytes) that an upload will be before it gets streamed to the file system
FILE_UPLOAD_MAX_MEMORY_SIZE = 3145728  # 1024*1024*3

# Braintree Configuration
# Note: the credentials must be valid for the selected BRAINTREE_ENV else get AuthenticationError
BRAINTREE_ENV = braintree.Environment.Production if ENV_TYPE == ENV_PROD else braintree.Environment.Sandbox
braintree.Configuration.configure(
    BRAINTREE_ENV,
    merchant_id=get_environment_variable('ORBIT_BRAINTREE_MERCHID'),
    public_key=get_environment_variable('ORBIT_BRAINTREE_PUBLIC_KEY'),
    private_key=get_environment_variable('ORBIT_BRAINTREE_PRIVATE_KEY')
)

# PayPal
PAYPAL_CLIENTID = get_environment_variable('PAYPAL_CLIENTID')
PAYPAL_SECRET = get_environment_variable('PAYPAL_SECRET')
PAYPAL_APP_NAME = get_environment_variable('PAYPAL_APP_NAME')
# set API_BASE_URL based on env
PAYPAL_API_BASEURL = 'https://api.paypal.com/v1/' if ENV_TYPE == ENV_PROD else 'https://api.sandbox.paypal.com/v1/'

#
# Auth0
#
# environment vars
AUTH0_CLIENTID = get_environment_variable('ORBIT_AUTH0_CLIENTID')
AUTH0_SECRET = get_environment_variable('ORBIT_AUTH0_SECRET')
AUTH0_DOMAIN = get_environment_variable('ORBIT_AUTH0_DOMAIN')

AUTHENTICATION_BACKENDS = (
    'users.auth_backends.Auth0Backend',
    'django.contrib.auth.backends.ModelBackend',
)

#
# DRF
#
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'PAGE_SIZE': 100,
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        # OAuth
        'oauth2_provider.ext.rest_framework.OAuth2Authentication',
    )
}

# OAuth
OAUTH2_PROVIDER = {
    'ACCESS_TOKEN_EXPIRE_SECONDS': APP_EXPIRE_SECONDS,
    # this is the list of available scopes
    'SCOPES': {'read': 'Read scope', 'write': 'Write scope', 'groups': 'Access to your groups'}
}

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',  # required by admin interface
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mysite.urls'

PDF_TEMPLATES_DIR = os.path.join(BASE_DIR, 'pdf_templates')

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'mysite.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME':     get_environment_variable('ORBIT_DB_NAME'),
        'USER':     get_environment_variable('ORBIT_DB_USER'),
        'PASSWORD': get_environment_variable('ORBIT_DB_PASSWORD'),
        'HOST':     get_environment_variable('ORBIT_DB_HOST')
    }
}

# Password validation
# https://docs.djangoproject.com/en/1.10/ref/settings/#auth-password-validators

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

# Password hashers
# https://docs.djangoproject.com/en/1.10/topics/auth/passwords/
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.BCryptPasswordHasher',
]

# Internationalization
# https://docs.djangoproject.com/en/1.10/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'
LOCAL_TIME_ZONE = 'America/Los_Angeles'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.10/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]
STATIC_ROOT = os.path.join(BASE_DIR, 'collected_static')

# auth settings (for server-side login/logout)
LOGIN_URL = 'ss-login'      # named url pattern
LOGIN_REDIRECT_URL = 'api-docs' # ,,

SWAGGER_SETTINGS = {
    'LOGIN_URL': 'ss-login',
    'LOGOUT_URL': 'ss-logout',
    'USE_SESSION_AUTH': True,
}

#
# logging configuration.
#
LOGDNA_API_KEY = get_environment_variable('ORBIT_LOGDNA_API_KEY')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            '()': 'django.utils.log.ServerFormatter',
            'format': '[%(server_time)s] %(levelname)-8s : %(message)s',
        },
        'verbose': {
            '()': 'django.utils.log.ServerFormatter',
            #'format': '[%(server_time)s] %(levelname)-8s %(name)-15s %(process)d %(thread)d %(lineno)-6s: %(message)s',
            'format': '[%(server_time)s] %(levelname)-8s %(name)-15s %(lineno)-6s: %(message)s',
        },
        # requires extra context key: requser (request.user)
        'req_fmt': {
            '()': 'django.utils.log.ServerFormatter',
            'format': '[%(server_time)s] %(levelname)-8s %(name)-15s %(requser)-20s: %(message)s',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue'
        },
    },
    'handlers': {
        # custom handler for LogDNA
        'logdna': {
            'level':  'DEBUG',
            'class': 'mysite.logdna_c.LogDNAHandlerCustom',
            'key': get_environment_variable('ORBIT_LOGDNA_API_KEY'),
            'options' : {
                'hostname': SERVER_HOSTNAME,
                'app': ENV_TYPE,
                'index_meta': True
            }
        },
        'null': {
            'level': 'DEBUG',
            'class': 'logging.NullHandler'
        },
        'console': {
            'class': 'logging.StreamHandler',
            'filters': ['require_debug_true'],
            'formatter': 'simple',
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        },
        'gen_rotfile': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'verbose',
            'filename': os.path.join(LOG_DIR, 'general.log'),
            'maxBytes': 2**18,
            'backupCount':5
        },
        'req_rotfile': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'req_fmt',
            'filename': os.path.join(LOG_DIR, 'requests.log'),
            'maxBytes': 2**18,
            'backupCount':5
        },
        'mgmt_rotfile': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'verbose',
            'filename': os.path.join(LOG_DIR, 'mgmt.log'),
            'maxBytes': 2**18,
            'backupCount':3
        },
    },
    'loggers': {
        'django.security.DisallowedHost': {
            'handlers': ['null',], # do not send email about Invalid HTTP_HOST header error
            'propagate': False,
        },
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
        'api': {
            'handlers': ['req_rotfile', 'mail_admins',],
            'level': 'DEBUG',
            'propagate': True,
        },
        'gen': {
            'handlers': ['gen_rotfile', 'mail_admins',],
            'level': 'DEBUG',
            'propagate': True,
        },
        'mgmt': {
            'handlers': ['mgmt_rotfile', 'mail_admins',],
            'level': 'DEBUG',
            'propagate': True,
        }
    }
}

EMAIL_HOST = 'email-smtp.us-west-2.amazonaws.com'
EMAIL_HOST_USER = 'AKIAIK23BTEAQYLOOY7A'
EMAIL_HOST_PASSWORD = 'AgG/jOFIGS94d4+Kti8elcIutjuBFaueNyU2bsCSpdLp'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_FROM = 'mission-control@orbitcme.com'
EMAIL_VERIFICATION_SUBJECT = 'Orbit email verification'
# used for error reporting
SERVER_EMAIL = EMAIL_FROM
# recipient for user feedback
FEEDBACK_RECIPIENT_EMAIL = 'feedback@orbitcme.com'
SUPPORT_EMAIL = 'support@orbitcme.com'
SALES_EMAIL = 'sales@orbitcme.com'
#SALES_EMAIL = 'faria.chowdhury@gmail.com'

HASHIDS_SALT = 'random jOFIGS94d4+Kti8elcIutjuBFaueNyU2bsCSpdLp'
DOCUMENT_HASHIDS_SALT = 'random AlVkkUk2Z14FCTXu1pC32pUYm3T6uYSEYZY9ZtOLVNEJ'
REPORT_HASHIDS_SALT = 'random AjMAVYQgiOgeS4Kwijb6ejHTzsMNsqvsauMIooVlxkOA'

# Tufts license start/end dates that are printed on Certificates
CERT_ORIGINAL_RELEASE_DATE = datetime(2017, 8, 7, tzinfo=pytz.utc)
CERT_EXPIRE_DATE = datetime(2018, 8, 6, tzinfo=pytz.utc)
# Separate dates for Orbit Story Certificates
STORY_CERT_ORIGINAL_RELEASE_DATE = datetime(2018, 3, 1, tzinfo=pytz.utc)
STORY_CERT_EXPIRE_DATE = datetime(2019, 3, 1, tzinfo=pytz.utc)

# Company details (printed on Certificate)
COMPANY_NAME = 'Transcend Review Inc.'
COMPANY_BRN_CEP = 'BRN CEP#16946'
COMPANY_ADDRESS = '265 Cambridge Ave, #61224, Palo Alto CA 94306'
