import os
from pprint import pprint
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from social.apps.django_app.utils import psa
# proj
from common.viewutils import render_to_json_response
# app
from .oauth_tools import get_access_token, delete_access_token

TPL_DIR = 'users'

def ss_login(request):
    #print("host: {0}".format(request.get_host())) # to test if nginx passes correct host to django
    return render(request, os.path.join(TPL_DIR, 'login.html'))

def ss_login_error(request):
    return render(request, os.path.join(TPL_DIR, 'login_error.html'))

@login_required()
def ss_home(request):
    return render(request, os.path.join(TPL_DIR, 'home.html'))

def ss_logout(request):
    print('logout {0}'.format(request.user))
    auth_logout(request)
    return render(request, os.path.join(TPL_DIR, 'logged_out.html'))


# http://psa.matiasaguirre.net/docs/use_cases.html#signup-by-oauth-access-token
# Client passes fb access token as GET parameter.
# Server logs in the user, and returns user info, and internal access_token
@psa('social:complete')
def login_via_token(request, backend):
    """
    This view expects an access_token GET parameter.
    request.backend and request.strategy will be loaded with the current
    backend and strategy.
    """
    key = 'access_token'
    token = request.GET.get(key)
    if key not in request.GET or not token:
        context = {
            'success': False,
            'error_message': 'Invalid GET parameter'
        }
        return render_to_json_response(context, status_code=400)
    user = request.backend.do_auth(token)
    if user:
        auth_login(request, user)
        user_dict = {
            'id': user.pk,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
        }
        context = {
            'success': True,
            'token': get_access_token(user),
            'user': user_dict
        }
        pprint(context)
        return render_to_json_response(context)
    else:
        context = {
            'success': False,
            'error_message': 'User authentication failed'
        }
        return render_to_json_response(context, status_code=400)


def logout_via_token(request):
    key = 'access_token'
    token = request.GET.get(key)
    if key not in request.GET or not token:
        context = {
            'success': False,
            'error_message': 'Invalid GET parameter'
        }
        return render_to_json_response(context, status_code=400)
    if request.user.is_authenticated:
        print('logout {0}'.format(request.user))
        delete_access_token(request.user, token)
        auth_logout(request)
    context = {'success': True}
    return render_to_json_response(context)
