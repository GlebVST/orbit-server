#
# python-social-auth settings
# Note: Key and secret are stored as environment vars
#
# http://python-social-auth.readthedocs.io/en/latest/backends/facebook.html
SOCIAL_AUTH_FACEBOOK_SCOPE = ['email','public_profile']
# http://stackoverflow.com/questions/21968004/how-to-get-user-email-with-python-social-auth-with-facebook-and-save-it
# http://stackoverflow.com/questions/32024327/facebook-doesnt-return-email-python-social-auth
# https://developers.facebook.com/docs/facebook-login/permissions#reference-public_profile
SOCIAL_AUTH_FACEBOOK_PROFILE_EXTRA_PARAMS = {
    #'fields': 'id,name,email,first_name,last_name,link,picture',
    'fields': 'id,name,email,first_name,last_name,link',
}
# Django Admin
# http://psa.matiasaguirre.net/docs/configuration/django.html
SOCIAL_AUTH_ADMIN_USER_SEARCH_FIELDS = ['username', 'first_name', 'email']
# http://psa.matiasaguirre.net/docs/configuration/settings.html
SOCIAL_AUTH_LOGIN_ERROR_URL = '/auth/ss-login-error/'  # must match urls.py
SOCIAL_AUTH_SANITIZE_REDIRECTS = True # redirect after login must be to same domain as login url
