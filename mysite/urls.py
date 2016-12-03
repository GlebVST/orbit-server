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
from users import views, auth_views, debug_views, payment_views
from common.swagger import SwaggerCustomUIRenderer
from rest_framework.decorators import api_view, renderer_classes, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework import response, schemas
from rest_framework.renderers import CoreJSONRenderer
from rest_framework_swagger.renderers import OpenAPIRenderer
from django.contrib.auth.decorators import login_required

auth_patterns = [
    # site login via server-side fb login (for testing only)
    url(r'^ss-login/?$', auth_views.ss_login, name='ss-login'),
    url(r'^ss-login-error/?$', auth_views.ss_login_error, name='ss-login-error'),
    url(r'^ss-home/?$', auth_views.ss_home, name='ss-home'),
    url(r'^ss-logout/?$', auth_views.ss_logout, name='ss-logout'),
]

payment_patterns = [
    url(r'^test-form/$', payment_views.TestForm.as_view(), name='payment-test-form'),
]

api_patterns = [
    # AUTH
    url(r'^auth/status/?$', auth_views.auth_status, name='get-status'),
    # client gets fb access token and exchanges it for internal token, and login user
    url(r'^auth/login/(?P<backend>[^/]+)/(?P<access_token>[^/]+)/?$', auth_views.login_via_token, name='login-via-token'),
    # client requests to revoke internal token and logout user
    url(r'^auth/logout/?$', auth_views.logout_via_token, name='logout-via-token'),

    # BRAINTREE & SHOP
    url(r'^shop/client-token/?$', payment_views.GetToken.as_view(), name='get-client-token'),
    url(r'^shop/client-methods/?$', payment_views.GetPaymentMethods.as_view(), name='get-client-payment-methods'),
    url(r'^shop/checkout/?$', payment_views.Checkout.as_view(), name='payment-checkout'),
    url(r'^shop/purchase-options/?$', views.PPOList.as_view(), name='shop-options'),

    # Account and Profile-related
    url(r'^accounts/?$', views.CustomerList.as_view()),
    url(r'^accounts/(?P<pk>[0-9]+)/?$', views.CustomerDetail.as_view()),
    url(r'^profiles/?$', views.ProfileList.as_view()),
    url(r'^profiles/(?P<pk>[0-9]+)/?$', views.ProfileDetail.as_view()),
    url(r'^cmetags/?$', views.CmeTagList.as_view()),
    url(r'^cmetags/(?P<pk>[0-9]+)/?$', views.CmeTagDetail.as_view()),
    url(r'^degrees/?$', views.DegreeList.as_view()),
    url(r'^degrees/(?P<pk>[0-9]+)/?$', views.DegreeDetail.as_view()),
    url(r'^practice-specialties/?$', views.PracticeSpecialtyList.as_view()),
    url(r'^practice-specialties/(?P<pk>[0-9]+)/?$', views.PracticeSpecialtyDetail.as_view()),

    # Feed entry types
    url(r'^entrytypes/?$', views.EntryTypeList.as_view()),
    url(r'^entrytypes/(?P<pk>[0-9]+)/?$', views.EntryTypeDetail.as_view()),

    # FEED
    url(r'^feed/?$', views.FeedList.as_view()),
    url(r'^feed/(?P<pk>[0-9]+)/?$', views.FeedEntryDetail.as_view()),
    url(r'^feed/browser-cme-offers/?$', views.BrowserCmeOfferList.as_view()),
    ##url(r'^feed/browser-cme-offer/?$', views.GetBrowserCmeOffer.as_view()),
    url(r'^feed/browser-cme/?$', views.CreateBrowserCme.as_view()),
    url(r'^feed/browser-cme/(?P<pk>[0-9]+)/?$', views.UpdateBrowserCme.as_view()),
    url(r'^feed/cme/?$', views.CreateSRCme.as_view()),
    url(r'^feed/cme-spec/?$', views.CreateSRCmeSpec.as_view()),
    url(r'^feed/cme/(?P<pk>[0-9]+)/?$', views.UpdateSRCme.as_view()),

    # user feedback (list/create)
    url(r'^feedback/?$', views.UserFeedbackList.as_view()),

    # debug
    url(r'^debug/make-browser-cme-offer/?$', debug_views.MakeBrowserCmeOffer.as_view()),
    url(r'^debug/feed/reward/?$', debug_views.MakeRewardEntry.as_view()),
]

# Custom view to render Swagger UI consuming only /api/ endpoints
@login_required()
@api_view()
@authentication_classes((SessionAuthentication,))
@renderer_classes([CoreJSONRenderer, OpenAPIRenderer, SwaggerCustomUIRenderer])
@permission_classes((IsAuthenticated,))
def swagger_view(request):
    patterns = url(r'^api/v1/', include(api_patterns)),
    generator = schemas.SchemaGenerator(title='Orbit API', patterns=patterns)
    return response.Response(generator.get_schema())


urlpatterns = [
    # Swagger
    url(r'^api-docs/', swagger_view, name='api-docs'),
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
