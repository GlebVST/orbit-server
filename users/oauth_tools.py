from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from oauth2_provider.settings import oauth2_settings
from oauthlib.common import generate_token
from oauth2_provider.models import AccessToken, Application, RefreshToken
from django.utils.timezone import now, timedelta

APP_NAME = 'orbit'

def get_token_dict(access_token):
    """
    Takes an AccessToken instance as an argument
    and returns a dict from that AccessToken.
    """
    token = {
        'access_token': access_token.token,
        'expires_in': oauth2_settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        'token_type': 'Bearer',
        'refresh_token': access_token.refresh_token.token,
        'scope': access_token.scope
    }
    return token

def get_access_token(user):
    """
    Takes a user instance and return an access_token as a dict if available
    """
    # our oauth2 app
    app = Application.objects.get(name=APP_NAME)

    try:
        access_token = AccessToken.objects.get(application=app, user=user)
    except ObjectDoesNotExist:
        return None
    except MultipleObjectsReturned:
        access_token = AccessToken.objects.filter(application=app, user=user).order_by('-expires')[0]
    # serialize token
    if not access_token.is_expired():
        return get_token_dict(access_token)
    return None

def new_access_token(user):
    """
    Takes a user instance and return a new access_token as a dict
    """
    # our oauth2 app
    app = Application.objects.get(name=APP_NAME)
    # delete the old access_token and refresh_token
    try:
        old_access_token = AccessToken.objects.get(application=app, user=user)
        old_refresh_token = RefreshToken.objects.get(application=app, user=user, access_token=old_access_token)
        old_access_token.delete()
        old_refresh_token.delete()
    except ObjectDoesNotExist:
        pass
    except MultipleObjectsReturned:
        qset = AccessToken.objects.filter(application=app, user=user)
        for old_access_token in qset:
            old_access_token.delete()
        qset = RefreshToken.objects.filter(application=app, user=user)
        for old_refresh_token in qset:
            old_refresh_token.delete()

    # generate a new access token, and refresh token
    token = generate_token()
    refresh_token = generate_token()
    expires = now() + timedelta(seconds=oauth2_settings.ACCESS_TOKEN_EXPIRE_SECONDS)
    scope = "read write"

    # create the access token
    # https://django-oauth-toolkit.readthedocs.io/en/latest/models.html
    access_token = AccessToken.objects.create(
        user=user,
        application=app,
        expires=expires,
        token=token,
        scope=scope)

    # create the refresh token
    RefreshToken.objects.create(
        user=user,
        application=app,
        token=refresh_token,
        access_token=access_token)

    # return access token as dict
    return get_token_dict(access_token)


def delete_access_token(user, token):
    """Delete access token and refresh_token"""
    app = Application.objects.get(name=APP_NAME)
    # delete the access_token and refresh_token
    try:
        access_token = AccessToken.objects.get(application=app, token=token, user=user)
        refresh_token = RefreshToken.objects.get(application=app, access_token=access_token, user=user)
    except ObjectDoesNotExist:
        pass
    else:
        access_token.delete()
        refresh_token.delete()
