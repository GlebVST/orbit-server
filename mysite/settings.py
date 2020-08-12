"""
Django settings for mysite project.

Generated by 'django-admin startproject' using Django 1.10.1.
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
    ('Gleb Starodubstev',   'gleb@codeabovelab.com')
]

MANAGERS = [
    ('Ram Srinivasan',     'ram@orbitcme.com'),
    ('Faria Chowdhury',     'faria.chowdhury@gmail.com'),
    ('Naoki Eto',   'logicalmath333@gmail.com')
]
DEV_EMAILS = [
    'faria@orbitcme.com',
    'logicalmath333@gmail.com',
]

# Note: This value should match the X_FORWARDED_HOST in the nginx conf file.
SERVER_HOSTNAME = get_environment_variable('ORBIT_SERVER_HOSTNAME')  # e.g. test1.orbitcme.com
SERVER_IP = os.environ.get('ORBIT_SERVER_IP_ADDR', '')
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]', SERVER_HOSTNAME]
if SERVER_IP:
    ALLOWED_HOSTS.append(SERVER_IP)

# This value used by various expiration-related settings
APP_EXPIRE_SECONDS = 86400*90  # 90 days

# Application definition

INSTALLED_APPS = [
    'dal', # 3rd party package: django-autocomplete-light (dal)
    'dal_select2', # ,,
    'dal_admin_filters',  # extra 3rd party package that depends on dal
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.postgres',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'storages',
    'users.apps.UsersConfig',
    'goals.apps.GoalsConfig',
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
ORG_MEDIA_BASEDIR = 'org'
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
AUTH0_DOMAIN = get_environment_variable('ORBIT_AUTH0_DOMAIN')
AUTH0_CLIENTID = get_environment_variable('ORBIT_AUTH0_CLIENTID')
AUTH0_SECRET = get_environment_variable('ORBIT_AUTH0_SECRET')
AUTH0_AUDIENCE = get_environment_variable('ORBIT_AUTH0_AUDIENCE')
AUTH0_SPA_CLIENTID = get_environment_variable('ORBIT_AUTH0_SPA_CLIENTID')
AUTH0_SPA_SECRET = get_environment_variable('ORBIT_AUTH0_SPA_SECRET')
AUTH0_MGMT_CLIENTID = get_environment_variable('ORBIT_AUTH0_MGMT_CLIENTID')
AUTH0_MGMT_SECRET = get_environment_variable('ORBIT_AUTH0_MGMT_CLIENT_SECRET')

# MailChimp
ORBIT_MAILCHIMP_USERNAME = get_environment_variable('ORBIT_MAILCHIMP_USERNAME')
ORBIT_MAILCHIMP_API_KEY = get_environment_variable('ORBIT_MAILCHIMP_API_KEY')
ORBIT_EMAIL_SYNC_LIST_NAME = get_environment_variable('ORBIT_MAILCHIMP_SUBSCRIBERS_LIST')
ORBIT_EMAIL_SYNC_LIST_ID = get_environment_variable('ORBIT_MAILCHIMP_LIST_ID')

DEFAULT_ESP = "Mailchimp"

# Google auth service account
GAUTH_SERVICE_CREDENTIALS_FILE = os.path.join(BASE_DIR, 'conf', 'orbit-274702-1a3cc79cd678.json')
GSHEET_TUFTS_EVAL_DOCID = get_environment_variable('ORBIT_GSHEET_TUFTS_EVAL_DOCID')

AUTHENTICATION_BACKENDS = (
    'users.auth_backends.ImpersonateBackend',
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
        'rest_framework_jwt.authentication.JSONWebTokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ),
}

# JWT Auth - used by drf-jwt library
JWT_AUTH = {
    'JWT_PAYLOAD_GET_USERNAME_HANDLER': 'users.jwtauthutils.jwt_get_username_from_payload_handler',
    'JWT_DECODE_HANDLER': 'users.jwtauthutils.jwt_decode_token',
    'JWT_ALGORITHM': 'RS256',
    'JWT_AUDIENCE': AUTH0_AUDIENCE,
    'JWT_ISSUER': 'https://' + AUTH0_DOMAIN + '/',
    'JWT_AUTH_HEADER_PREFIX': 'Bearer'
}

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.RemoteUserMiddleware',   # added for auth0
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
LOGIN_REDIRECT_URL = 'ss-home' # ,,

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
            'format': '[%(asctime)s] %(levelname)-8s : %(message)s',
        },
        'verbose': {
            '()': 'django.utils.log.ServerFormatter',
            'format': '[%(asctime)s] %(levelname)-8s %(name)-15s %(lineno)-6s: %(message)s',
        },
        # requires extra context key: requser (request.user)
        'req_fmt': {
            '()': 'django.utils.log.ServerFormatter',
            'format': '[%(asctime)s] %(levelname)-8s %(name)-15s %(requser)-20s: %(message)s',
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
            'backupCount': 7
        },
        'req_rotfile': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'req_fmt',
            'filename': os.path.join(LOG_DIR, 'requests.log'),
            'maxBytes': 2**18,
            'backupCount':7
        },
        'mgmt_rotfile': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'verbose',
            'filename': os.path.join(LOG_DIR, 'mgmt.log'),
            'maxBytes': 2**18,
            'backupCount':7
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
EMAIL_SUBJECT_PREFIX = '[Orbit] ' if ENV_TYPE == ENV_PROD else '[Orbit Test] '

# recipient for user feedback
FEEDBACK_RECIPIENT_EMAIL = 'feedback@orbitcme.com'
SUPPORT_EMAIL = 'support@orbitcme.com'
SALES_EMAIL = 'sales@orbitcme.com'
#SALES_EMAIL = 'faria@orbitcme.com'
FOUNDER_EMAIL = 'ram@orbitcme.com'

HASHIDS_SALT = 'random jOFIGS94d4+Kti8elcIutjuBFaueNyU2bsCSpdLp'
DOCUMENT_HASHIDS_SALT = 'random AlVkkUk2Z14FCTXu1pC32pUYm3T6uYSEYZY9ZtOLVNEJ'
REPORT_HASHIDS_SALT = 'random AjMAVYQgiOgeS4Kwijb6ejHTzsMNsqvsauMIooVlxkOA'

# celery settings
CELERY_BROKER_URL = 'redis://localhost:6379/0'  # redis://:password@hostname:port/db_number
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
##CELERY_IGNORE_RESULT = False  # enable for testing results only
CELERY_ACCEPT_CONTENT = ['json',]
CELERY_TASK_SERIALIZER = 'json'
CELERY_IMPORTS = ['users.tasks',]

# The ABA (ACCME) ID is used to submit CME data to ABA (American Board of Anesthesiology)
ABA_ACCME_ID = 'LP392'
# Email recipient for CME data submission
ABA_CME_EMAIL = 'cme@theaba.org'

# Tufts license start/end dates that are printed on Certificates
CERT_ORIGINAL_RELEASE_DATE = datetime(2017, 8, 7, tzinfo=pytz.utc)
CERT_EXPIRE_DATE = datetime(2022, 8, 6, tzinfo=pytz.utc)
# Separate dates for Orbit Story Certificates
STORY_CERT_ORIGINAL_RELEASE_DATE = datetime(2018, 3, 1, tzinfo=pytz.utc)
STORY_CERT_EXPIRE_DATE = datetime(2019, 3, 1, tzinfo=pytz.utc)

# Company details (printed on Certificate)
COMPANY_NAME = 'Transcend Review, Inc.'
COMPANY_BRN_CEP = 'BRN CEP#16946'
COMPANY_ADDRESS = '265 Cambridge Ave, #61224, Palo Alto CA 94306'

ORBIT_LOGO_BLUE = 'https://orbitcme.com/assets/images/login-logo.png'
ORBIT_LOGO_WHITE = 'https://orbitcme.com/assets/images/logo.png'

# UI links (relative to SERVER_HOSTNAME)
UI_LINK_SUBSCRIPTION = '/subscription'
UI_LINK_FEEDBACK = '/feedback'
UI_LINK_LOGIN = '/login'
UI_LINK_JOINTEAM = '/join-team'

# This is the default welcome article used to generate the first offer.
#It can be overriden by SubscriptionPlan.welcome_offer_url
WELCOME_ARTICLE_URL = 'https://jamanetwork.com/journals/jamadermatology/fullarticle/412635'
WELCOME_ARTICLE_TITLE = 'Fluoroscopy-Induced Chronic Radiation Skin Injury: A Disease Perhaps Often Overlooked'

MIN_CME_CREDIT_FOR_REFERRAL = 5
MAX_TRIAL_CME_CREDIT = 2
