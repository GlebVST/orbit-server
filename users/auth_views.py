import os
import json
import logging
from auth0.v3.authentication import GetToken, Users
from django.conf import settings
from django.contrib.auth import  authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
# proj
from common.logutils import *
import common.appconstants as appconstants
# app
from .oauth_tools import new_access_token, get_access_token, delete_access_token
from .models import *
from .serializers import ReadProfileSerializer, CmeTagSerializer, ActiveCmeTagSerializer, ReadUserSubsSerializer, StateLicenseSerializer, ReadInvitationDiscountSerializer

logger = logging.getLogger('api.auth')
TPL_DIR = 'users'

# Used in development and to allow access to Swagger UI.
CALLBACK_URL = 'http://localhost:8000/auth/auth0-cb-login' # used by login_via_code for server-side login only
if settings.ENV_TYPE == settings.ENV_PROD:
    CALLBACK_URL = 'https://admin.orbitcme.com/auth/auth0-cb-login' # must be added to callback url for auth0 client settings

def ss_login(request):
    msg = "host: {0}".format(request.get_host())
    # to test if nginx passes correct host to django
    logDebug(logger, request, msg)
    context = {
        'AUTH0_CLIENTID': settings.AUTH0_CLIENTID,
        'AUTH0_DOMAIN': settings.AUTH0_DOMAIN,
        'CALLBACK_URL': CALLBACK_URL
    }
    return render(request, os.path.join(TPL_DIR, 'login.html'), context)

def ss_login_error(request):
    return render(request, os.path.join(TPL_DIR, 'login_error.html'))

@login_required()
def ss_home(request):
    return render(request, os.path.join(TPL_DIR, 'home.html'))

def ss_logout(request):
    auth_logout(request)
    return render(request, os.path.join(TPL_DIR, 'logged_out.html'))

# Used by ss-login only
def login_via_code(request):
    """
    This view expects a query parameter called code.
    Server logs in the user, and returns user info, and internal access_token

    """
    code = request.GET.get('code')
    if not code:
        return HttpResponse(status=400)
    remote_addr = request.META.get('REMOTE_ADDR')
    get_token = GetToken(settings.AUTH0_DOMAIN)
    auth0_users = Users(settings.AUTH0_DOMAIN)
    token = get_token.authorization_code(
        settings.AUTH0_CLIENTID,
        settings.AUTH0_SECRET,
        code,
        CALLBACK_URL
    )
    user_info = auth0_users.userinfo(token['access_token'])
    user_info_dict = json.loads(user_info)
    logInfo(logger, request, 'user_id: {user_id} email:{email}'.format(**user_info_dict))
    user = authenticate(user_info=user_info_dict) # must specify the keyword user_info
    if user:
        auth_login(request, user)
        token = new_access_token(user)
        logDebug(logger, request, 'login from ip: ' + remote_addr)
        return redirect('api-docs')
    else:
        context = {
            'success': False,
            'message': 'User authentication failed'
        }
        msg = context['message'] + ' from ip: ' + remote_addr
        logDebug(logger, request, msg)
        return redirect('ss-login-error')


def serialize_user(user):
    return {
        'id': user.pk,
        'email': user.email,
        'username': user.username
    }


def serialize_customer(customer):
    return {
        'customerId': customer.customerId
    }

def serialize_permissions(user, user_subs):
    """
    user_subs_perms: Permission queryset of the allowed permissions for the user
    Returns list of dicts: [{codename:str, allowed:bool}]
    for the permissions in appconstants.ALL_PERMS.
    """
    allowed_codes = []
    # get any special admin groups that user is a member of
    for g in user.groups.all():
        allowed_codes.extend([p.codename for p in g.permissions.all()])
    if user_subs:
        user_subs_perms = UserSubscription.objects.getPermissions(user_subs) # Permission queryset
        allowed_codes.extend([p.codename for p in user_subs_perms])
    allowed_codes = set(allowed_codes)
    perms = [{
            'codename': codename,
            'allow': codename in allowed_codes
        } for codename in appconstants.ALL_PERMS]
    #print(perms)
    return perms

def serialize_subscription(user_subs):
    s = ReadUserSubsSerializer(user_subs)
    return s.data

def serialize_profile(profile):
    s = ReadProfileSerializer(profile)
    return s.data

def serialize_active_cmetag(tag):
    s = ActiveCmeTagSerializer(tag)
    return s.data

def serialize_statelicense(obj):
    return StateLicenseSerializer(obj).data

def serialize_invitationDiscount(obj):
    return ReadInvitationDiscountSerializer(obj).data

def make_login_context(token, user):
    """Create context dict for response.
    Args:
        token: dict - internal access token details
        user: User instance
    """
    customer = Customer.objects.get(user=user)
    profile = Profile.objects.get(user=user)
    user_subs = UserSubscription.objects.getLatestSubscription(user)
    if user_subs:
        UserSubscription.objects.checkTrialToActive(user_subs)
    sacme_tag = CmeTag.objects.get(name=CMETAG_SACME)
    context = {
        'success': True,
        'token': token,
        'user': serialize_user(user),
        'profile': serialize_profile(profile),
        'customer': serialize_customer(customer),
        'sacmetag': serialize_active_cmetag(sacme_tag),
        'statelicense': None,
        'invitation': None
    }
    context['subscription'] = serialize_subscription(user_subs) if user_subs else None
    context['allowTrial'] = user_subs is None  # allow a trial period if user has never had a subscription
    context['permissions'] = serialize_permissions(user, user_subs)
    context['creditTypes'] = [
        dict(value=Entry.CREDIT_CATEGORY_1, label=Entry.CREDIT_CATEGORY_1_LABEL, needs_tm=True),
        dict(value=Entry.CREDIT_OTHER, label=Entry.CREDIT_OTHER_LABEL, needs_tm=False)
    ]
    # 2017-08-15: add single object for user state license if exist
    if user.statelicenses.exists():
        context['statelicense'] = serialize_statelicense(user.statelicenses.all()[0])
    # 2017-08-29: add total number of completed InvitationDiscount for which user=inviter and total inviter-discount amount earned so far
    numCompleteInvites = InvitationDiscount.objects.getNumCompletedForInviter(user)
    if numCompleteInvites:
        context['invitation'] = {
            'totalCompleteInvites': numCompleteInvites,
            'totalCredit': InvitationDiscount.objects.sumCreditForInviter(user)
        }
    return context


@api_view()
@permission_classes((AllowAny,))
def auth_status(request):
    """
    This checks if there is a user session already (given OAuth token for example)
    and if yes return user info with a previously generated token.
    If no user session yet - respond with 401 status so client has to login.

    """
    user = request.user
    if not user.is_authenticated():
        context = {
            'success': False,
            'message': 'User not authenticated'
        }
        return Response(context, status=status.HTTP_401_UNAUTHORIZED)
    token = get_access_token(user)
    if not token:
        context = {
            'success': False,
            'message': 'User not authenticated'
        }
        return Response(context, status=status.HTTP_401_UNAUTHORIZED)
    context = make_login_context(token, user)
    return Response(context, status=status.HTTP_200_OK)


@api_view()
@permission_classes((AllowAny,))
def login_via_token(request, access_token):
    """
    This view expects an auth0 access_token parameter as part of the URL.
    Server logs in the user, and returns user info, and internal access_token.

    parameters:
        - name: access_token
          description: auth0 access token obtained via external means like Javascript SDK
          required: true
          type: string
          paramType: form
    """
    remote_addr = request.META.get('REMOTE_ADDR')
    inviterId = request.GET.get('inviteid') # if present, this is the inviteId of the inviter
    affiliateId = request.GET.get('affid') # if present, this is the affiliateId of the converter
    auth0_users = Users(settings.AUTH0_DOMAIN)
    user_info = auth0_users.userinfo(access_token) # return str as json
    user_info_dict = json.loads(user_info) # create dict
    user_info_dict['inviterId'] = inviterId
    user_info_dict['affiliateId'] = affiliateId
    msg = 'user_id:{user_id} email:{email} v:{email_verified}'.format(**user_info_dict)
    if affiliateId:
        msg += " from-affl:{affiliateId}".format(**user_info_dict)
    elif inviterId:
        msg += " invitedBy:{inviterId}".format(**user_info_dict)
    logInfo(logger, request, msg)
    user = authenticate(user_info=user_info_dict) # must specify the keyword user_info
    if user:
        auth_login(request, user)
        token = new_access_token(user)
        logDebug(logger, request, 'login from ip: ' + remote_addr)
        context = make_login_context(token, user)
        return Response(context, status=status.HTTP_200_OK)
    else:
        context = {
            'success': False,
            'message': 'User authentication failed'
        }
        msg = context['message'] + ' from ip: ' + remote_addr
        logDebug(logger, request, msg)
        return Response(context, status=status.HTTP_400_BAD_REQUEST)

@api_view()
@permission_classes((IsAuthenticated,))
def logout_via_token(request):
    if request.user.is_authenticated():
        logDebug(logger, request, 'logout')
        token = get_access_token(request.user)
        delete_access_token(request.user, token.get('access_token'))
        auth_logout(request)
    context = {'success': True}
    return Response(context, status=status.HTTP_200_OK)
