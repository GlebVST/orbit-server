"""mysite URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf.urls import url, include
#from rest_framework import routers
from rest_framework.urlpatterns import format_suffix_patterns
from users import views
from users import auth_views
from users import payment_views

auth_patterns = [
    # client gets fb access token and exchanges it for internal token, and login user
    url(r'^login-via-token/(?P<backend>[^/]+)/?$', auth_views.login_via_token, name='login-via-token'),
    # client requests to revoke internal token and logout user
    url(r'^logout-via-token/?$', auth_views.logout_via_token, name='logout-via-token'),
    # site login via server-side fb login (for testing only)
    url(r'^ss-login/?$', auth_views.ss_login, name='ss-login'),
    url(r'^ss-login-error/?$', auth_views.ss_login_error, name='ss-login-error'),
    url(r'^ss-home/?$', auth_views.ss_home, name='ss-home'),
    url(r'^ss-logout/?$', auth_views.ss_logout, name='ss-logout'),
]

payment_patterns = [
    url(r'^test-form/$', payment_views.TestForm.as_view(), name='payment-test-form'),
    url(r'^get-token/?$', payment_views.GetToken.as_view(), name='payment-get-token'),
    url(r'^checkout/?$', payment_views.Checkout.as_view(), name='payment-checkout'),
]

api_patterns = [
    url(r'^degrees/?$', views.DegreeList.as_view()),
    url(r'^degrees/(?P<pk>[0-9]+)/?$', views.DegreeDetail.as_view()),
    url(r'^point-purchase-options/?$', views.PPOList.as_view()),
    url(r'^point-purchase-options/(?P<pk>[0-9]+)/?$', views.PPODetail.as_view()),
]
api_patterns = format_suffix_patterns(api_patterns) # what does this do?

urlpatterns = [
    # api
    url(r'^api/v1/', include(api_patterns)),
    # auth
    url(r'auth/', include(auth_patterns)),
    # payment
    url(r'payment/', include(payment_patterns)),
    # Django admin interface
    url(r'^admin/', admin.site.urls),
    # direct use of oauth2_provider (no psa). Useful for admin users who are not associated with any social account.
    url(r'^o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    # login for the drf browsable api
    # http://www.django-rest-framework.org/tutorial/4-authentication-and-permissions/
    url(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    # PSA
    url(r'', include('social.apps.django_app.urls', namespace='social')),
]
