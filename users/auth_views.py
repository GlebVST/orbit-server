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
# app
from .models import *
from .jwtauthutils import get_token_auth_header, decode_token
from .serializers import ProfileReadSerializer, ActiveCmeTagSerializer, UserSubsReadSerializer, InvitationDiscountReadSerializer
from .feed_serializers import CreditTypeSerializer

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
    Server logs in the user, and redirects to api-docs.
    """
    code = request.GET.get('code')
    if not code:
        return HttpResponse(status=400)
    get_token = GetToken(settings.AUTH0_DOMAIN)
    auth0_users = Users(settings.AUTH0_DOMAIN)
    token = get_token.authorization_code(
        settings.AUTH0_CLIENTID,
        settings.AUTH0_SECRET,
        code,
        CALLBACK_URL
    )
    user_info_dict = auth0_users.userinfo(token['access_token'])
    #print(user_info_dict)
    logInfo(logger, request, 'user_id: {user_id} email:{email}'.format(**user_info_dict))
    user = authenticate(request, remote_user=user_info_dict)
    if user:
        auth_login(request, user, backend='users.auth_backends.Auth0Backend')
        return redirect('api-docs')
    else:
        context = {
            'success': False,
            'message': 'User authentication failed'
        }
        return redirect('ss-login-error')


def serialize_user(user):
    return {
        'id': user.pk,
        'email': user.email,
        'username': user.username
    }


def serialize_subscription(user_subs):
    s = UserSubsReadSerializer(user_subs)
    return s.data

def serialize_profile(profile):
    s = ProfileReadSerializer(profile)
    return s.data

def serialize_active_cmetag(tag):
    s = ActiveCmeTagSerializer(tag)
    return s.data

def serialize_statelicense(obj):
    return StateLicenseSerializer(obj).data

def serialize_invitationDiscount(obj):
    return InvitationDiscountReadSerializer(obj).data

def serialize_creditTypes(profile):
    degs = profile.degrees.all()
    if degs:
        qset = CreditType.objects.getForDegree(degs[0])
    else:
        qset = CreditType.objects.getUniversal()
    s = CreditTypeSerializer(qset, many=True)
    return s.data

def make_login_context(user):
    """Create context dict for response.
    Args:
        user: User instance
    """
    profile = Profile.objects.get(user=user)
    user_subs = UserSubscription.objects.getLatestSubscription(user)
    if user_subs:
        UserSubscription.objects.checkTrialStatus(user_subs)
    sacme_tag = CmeTag.objects.get(name=CmeTag.SACME)
    context = {
        'success': True,
        'token': None,
        'user': serialize_user(user),
        'profile': serialize_profile(profile),
        'sacmetag': serialize_active_cmetag(sacme_tag),
        'invitation': None,
        'credits': None
    }
    context['subscription'] = serialize_subscription(user_subs) if user_subs else None
    context['allowTrial'] = user_subs is None  # allow a trial period if user has never had a subscription
    pdata = UserSubscription.objects.serialize_permissions(user, user_subs)
    context['permissions'] = pdata['permissions']
    context['credits'] = pdata['credits']
    context['creditTypes'] = serialize_creditTypes(profile)
    # 2017-08-29: add total number of completed InvitationDiscount for which user=inviter and total inviter-discount amount earned so far
    numCompleteInvites = InvitationDiscount.objects.getNumCompletedForInviter(user)
    if numCompleteInvites:
        context['invitation'] = {
            'totalCompleteInvites': numCompleteInvites,
            'totalCredit': InvitationDiscount.objects.sumCreditForInviter(user)
        }
    return context

@api_view()
def auth_debug(request):
    """To test decode_token
    """
    access_token = get_token_auth_header(request)
    if not access_token:
        context = {
            'success': False,
            'message': 'Invalid or missing access_token'
        }
        return Response(context, status=status.HTTP_401_UNAUTHORIZED)
    decoded = decode_token(access_token) # dict (same as the payload dict passed to jwt_get_username_from_payload)
    #print(decoded)
    context = {
        'success': True,
        'message': 'OK'
    }
    return Response(context, status=status.HTTP_200_OK)


@api_view()
#@permission_classes((AllowAny,))
def auth_status(request):
    """Called by UI to get user context for an authenticated user
    """
    if request.user.is_authenticated:
        if not request.session:
            auth_login(request, user, backend='users.auth_backends.Auth0Backend')
        context = make_login_context(request.user)
        return Response(context, status=status.HTTP_200_OK)
    # else, bad token
    context = {
        'success': False,
        'message': 'Invalid or missing access_token'
    }
    return Response(context, status=status.HTTP_401_UNAUTHORIZED)

@api_view()
def signup(request, bt_plan_id):
    """Called by UI for new user signup.
    Expected URL parameter: planId of the plan selected by user (for BT lookup)
    Optional GET parameters:
        inviteid: invite code of an existing Orbit user
        affid: affiliateId value for a particular AffiliateDetail instance
    Create new user and profile
    Return user context
    """
    inviterId = request.GET.get('inviteid') # if present, this is the inviteId of the inviter
    affiliateId = request.GET.get('affid') # if present, this is the affiliateId of the converter
    try:
        plan = SubscriptionPlan.objects.get(planId=bt_plan_id)
    except SubscriptionPlan.DoesNotExist:
        context = {
            'success': False,
            'message': 'User signup failed. Invalid plan.'
        }
        msg = "Invalid planId: {0}. No plan found".format(planId)
        logWarning(logger, request, msg)
        return Response(context, status=status.HTTP_400_BAD_REQUEST)
    access_token = get_token_auth_header(request)
    auth0_users = Users(settings.AUTH0_DOMAIN) # Authentication API
    # https://auth0.com/docs/api/authentication#user-profile
    user_info_dict = auth0_users.userinfo(access_token) # returns dict as of auth0 v3.9.1
    user_info_dict['planId'] = plan.planId
    user_info_dict['inviterId'] = inviterId
    user_info_dict['affiliateId'] = affiliateId
    msg = 'user_id:{user_id} email:{email} v:{email_verified} plan:{planId}'.format(**user_info_dict)
    if affiliateId:
        msg += " from-affl:{affiliateId}".format(**user_info_dict)
    elif inviterId:
        msg += " invitedBy:{inviterId}".format(**user_info_dict)
    logInfo(logger, request, msg)
    remote_addr = request.META.get('REMOTE_ADDR')
    user = authenticate(request, remote_user=user_info_dict) # creates User (and Profile)
    if user:
        auth_login(request, user)
        logDebug(logger, request, 'signup from ip: ' + remote_addr)
        context = make_login_context(user)
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
def logout(request):
    logDebug(logger, request, 'logout')
    auth_logout(request)
    context = {'success': True}
    return Response(context, status=status.HTTP_200_OK)
