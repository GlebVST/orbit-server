import os
import logging
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from social_django.utils import psa
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
# proj
from common.viewutils import render_to_json_response
from common.logutils import *
import common.appconstants as appconstants
# app
from .oauth_tools import new_access_token, get_access_token, delete_access_token
from .models import *
from .serializers import ProfileSerializer, CmeTagSerializer

logger = logging.getLogger('app.auth')
TPL_DIR = 'users'

def ss_login(request):
    msg = "host: {0}".format(request.get_host())
    # to test if nginx passes correct host to django
    logDebug(logger, request, msg)
    return render(request, os.path.join(TPL_DIR, 'login.html'))

def ss_login_error(request):
    return render(request, os.path.join(TPL_DIR, 'login_error.html'))

@login_required()
def ss_home(request):
    return render(request, os.path.join(TPL_DIR, 'home.html'))

def ss_logout(request):
    auth_logout(request)
    return render(request, os.path.join(TPL_DIR, 'logged_out.html'))

def serialize_user(user):
    return {
        'id': user.pk,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name
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
    return {
        'subscriptionId': user_subs.subscriptionId,
        'bt_status': user_subs.status,
        'display_status': user_subs.display_status,
        'billingStartDate': user_subs.billingStartDate,
        'billingEndDate': user_subs.billingEndDate
    }

def serialize_profile(profile):
    s = ProfileSerializer(profile)
    return s.data

def serialize_cmetag(tag):
    s = CmeTagSerializer(tag)
    return s.data

def make_login_context(user, token):
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
        'sacmetag': serialize_cmetag(sacme_tag),
        'cmetags': CmeTagSerializer(profile.cmeTags, many=True).data
    }
    context['subscription'] = serialize_subscription(user_subs) if user_subs else None
    context['allowTrial'] = user_subs is None  # allow a trial period if user has never had a subscription
    context['permissions'] = serialize_permissions(user, user_subs)
    return context

@api_view()
@permission_classes((AllowAny,))
def auth_status(request):
    """
    This view checks if there is a user session already (given OAuth token for example)
    and if yes just return a user info with a previously generated token.
    If no user session yet - will respond with 401 status so client will have to login.

    """
    user = request.user
    if not user.is_authenticated():
        context = {
            'success': False,
            'error_message': 'User not authenticated'
        }
        return render_to_json_response(context, status_code=401)
    token = get_access_token(user)
    if not token:
        context = {
            'success': False,
            'error_message': 'User not authenticated'
        }
        return render_to_json_response(context, status_code=401)
    context = make_login_context(user, token)
    return render_to_json_response(context)


# http://psa.matiasaguirre.net/docs/use_cases.html#signup-by-oauth-access-token
# Client passes fb access token as url parameter.
# Server logs in the user, and returns user info, and internal access_token
@psa('social:complete')
@api_view()
@permission_classes((AllowAny,))
def login_via_token(request, backend, access_token):
    """
    This view expects an access_token parameter as part of the URL.
    request.backend and request.strategy will be loaded with the current
    backend and strategy.

    parameters:
        - name: access_token
          description: Facebook token obtained via external means like Javascript SDK
          required: true
          type: string
          paramType: form

    """
    inviteId = request.GET.get('inviteid', None)
    if inviteId:
        request.backend.strategy.session_set('inviteid', inviteId)
    user = request.backend.do_auth(access_token)
    if user:
        auth_login(request, user)
        logDebug(logger, request, 'login')
        token = new_access_token(user)
        context = make_login_context(user, token)
        return render_to_json_response(context)
    else:
        context = {
            'success': False,
            'error_message': 'User authentication failed'
        }
        return render_to_json_response(context, status_code=400)


@api_view()
@permission_classes((IsAuthenticated,))
def logout_via_token(request):
    if request.user.is_authenticated():
        logDebug(logger, request, 'logout')
        token = get_access_token(request.user)
        delete_access_token(request.user, token.get('access_token'))
        auth_logout(request)
    context = {'success': True}
    return render_to_json_response(context)
