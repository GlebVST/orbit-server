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
# python-social-auth settings
from psa_config import *

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.10/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 's*l=k=*e@(jj2t6hk1er_g!6g5ztxp+n@90+@a1$nqn*(7mw(d'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]', '35.164.81.19']

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
    'social.apps.django_app.default',
    'users.apps.UsersConfig',
    'rest_framework_swagger'
]

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
# PSA auth backends
AUTHENTICATION_BACKENDS = (
    # Facebook OAuth2
    'social.backends.facebook.FacebookAppOAuth2',
    'social.backends.facebook.FacebookOAuth2',
    # Django
    'django.contrib.auth.backends.ModelBackend',
)
# PSA pipeline
SOCIAL_AUTH_PIPELINE = (
    'social.pipeline.social_auth.social_details',
    'social.pipeline.social_auth.social_uid',
    'social.pipeline.social_auth.auth_allowed',
    'social.pipeline.social_auth.social_user',
    'social.pipeline.user.get_username',
    'social.pipeline.user.create_user',
    'users.pipeline.save_profile',  # user profile/customer objects
    'social.pipeline.social_auth.associate_user',
    'social.pipeline.social_auth.load_extra_data',
    'social.pipeline.user.user_details',
)

# django-cors-headers
CORS_ORIGIN_ALLOW_ALL = True

#
# DRF
#
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'PAGE_SIZE': 10,
    'DEFAULT_AUTHENTICATION_CLASSES': (
        # OAuth
        'oauth2_provider.ext.rest_framework.OAuth2Authentication',
    )
}

# OAuth
OAUTH2_PROVIDER = {
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
                'social.apps.django_app.context_processors.backends',
                'social.apps.django_app.context_processors.login_redirect',
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

MEDIA_ROOT = os.path.join(BASE_DIR, 'user_media')
MEDIA_URL = '/user-media/'

# auth settings (for server-side login/logout)
LOGIN_URL = 'ss-login'      # named url pattern
LOGIN_REDIRECT_URL = 'api-docs' # ,,

SWAGGER_SETTINGS = {
    'LOGIN_URL': 'ss-login',
    'LOGOUT_URL': 'ss-logout',
    'USE_SESSION_AUTH': True,
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            '()': 'django.utils.log.ServerFormatter',
            'format': '[%(server_time)s] %(message)s',
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'users': {
            'handlers': ['console'],
            'level': 'DEBUG'
        }
    }
}
