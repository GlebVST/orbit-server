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
from distutils.util import strtobool
import logging
# python-social-auth settings
from psa_config import *

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.10/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 's*l=k=*e@(jj2t6hk1er_g!6g5ztxp+n@90+@a1$nqn*(7mw(d'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = bool(strtobool(os.environ.get('ORBIT_SERVER_DEBUG', 'false')))

ADMINS = [
    ('Faria Chowdhury', 'faria.chowdhury@gmail.com'),
]

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]', '192.168.0.37', 'test1.orbitcme.com']

# This value used by various expiration-related settings
APP_EXPIRE_SECONDS = 86400*30  # 30 days

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
    'social_django',
    'storages',
    'users.apps.UsersConfig',
    'rest_framework_swagger'
]

# Session
SESSION_COOKIE_AGE = APP_EXPIRE_SECONDS

# django-storages AWS S3
AWS_ACCESS_KEY_ID = os.environ.get('ORBIT_AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('ORBIT_AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.environ.get('ORBIT_AWS_S3_BUCKET_NAME')
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

# Braintree sandbox environment vars
braintree.Configuration.configure(
    braintree.Environment.Sandbox,
    merchant_id=os.environ.get('ORBIT_BRAINTREE_MERCHID'),
    public_key=os.environ.get('ORBIT_BRAINTREE_PUBLIC_KEY'),
    private_key=os.environ.get('ORBIT_BRAINTREE_PRIVATE_KEY')
)

#
# PSA
#
# PSA environment vars
SOCIAL_AUTH_FACEBOOK_KEY = os.environ.get('ORBIT_FB_AUTH_KEY')
SOCIAL_AUTH_FACEBOOK_SECRET = os.environ.get('ORBIT_FB_AUTH_SECRET')
if not DEBUG:
    SOCIAL_AUTH_REDIRECT_IS_HTTPS = True
SOCIAL_AUTH_STRATEGY = 'social_django.strategy.DjangoStrategy'
SOCIAL_AUTH_STORAGE = 'social_django.models.DjangoStorage'
# PSA auth backends
AUTHENTICATION_BACKENDS = (
    # Facebook OAuth2
    'social_core.backends.facebook.FacebookAppOAuth2',
    'social_core.backends.facebook.FacebookOAuth2',
    # Django
    'django.contrib.auth.backends.ModelBackend',
)
SOCIAL_AUTH_FIELDS_STORED_IN_SESSION = ['inviteid',]
# PSA pipeline
SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.user.create_user',
    'users.pipeline.save_profile',  # user profile/customer objects
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
    #'social_core.pipeline.debug.debug'   # may be causing broken pipe errors in runserver
)

#
# DRF
#
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'PAGE_SIZE': 100,
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
                # PSA
                'social_django.context_processors.backends',
                'social_django.context_processors.login_redirect',
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
        'NAME': os.environ.get('ORBIT_DB_NAME'),
        'USER': os.environ.get('ORBIT_DB_USER'),
        'PASSWORD': os.environ.get('ORBIT_DB_PASSWORD'),
        'HOST': os.environ.get('ORBIT_DB_HOST')
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
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
        'api': {
            'handlers': ['req_rotfile', 'gen_rotfile', 'mail_admins',],
            'level': 'DEBUG',
            'propagate': True,
        },
        'psa-pipeline': {
            'handlers': ['gen_rotfile', 'mail_admins'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'serializers': {
            'handlers': ['gen_rotfile', 'mail_admins',],
            'level': 'DEBUG',
            'propagate': True,
        },
    }
}

EMAIL_HOST = 'email-smtp.us-west-2.amazonaws.com'
EMAIL_HOST_USER = 'AKIAIK23BTEAQYLOOY7A'
EMAIL_HOST_PASSWORD = 'AgG/jOFIGS94d4+Kti8elcIutjuBFaueNyU2bsCSpdLp'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_FROM = 'mission-control@orbitcme.com'
EMAIL_VERIFICATION_SUBJECT = 'Orbit email verification'
DOMAIN_REFERENCE = 'test1.orbitcme.com'  # TODO: make this an environment var
# used for error reporting
SERVER_EMAIL = EMAIL_FROM


HASHIDS_SALT = 'random jOFIGS94d4+Kti8elcIutjuBFaueNyU2bsCSpdLp'
DOCUMENT_HASHIDS_SALT = 'random AlVkkUk2Z14FCTXu1pC32pUYm3T6uYSEYZY9ZtOLVNEJ'
REPORT_HASHIDS_SALT = 'random AjMAVYQgiOgeS4Kwijb6ejHTzsMNsqvsauMIooVlxkOA'
