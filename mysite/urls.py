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
from django.conf.urls import url, include
from django.conf import settings
from django.conf.urls.static import static
from users import views, auth_views, debug_views, payment_views, admin_views, ac_views
from users.admin import admin_site
from common.swagger import SwaggerCustomUIRenderer
from rest_framework.decorators import api_view, renderer_classes, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework import response, schemas
from rest_framework.renderers import CoreJSONRenderer
from rest_framework_swagger.renderers import OpenAPIRenderer

auth_patterns = [
    # site login via server-side login (for testing only)
    url(r'^ss-login/?$', auth_views.ss_login, name='ss-login'),
    url(r'^auth0-cb-login/?$', auth_views.login_via_code, name='login-via-code'),
    url(r'^ss-login-error/?$', auth_views.ss_login_error, name='ss-login-error'),
    url(r'^ss-home/?$', auth_views.ss_home, name='ss-home'),
    url(r'^ss-logout/?$', auth_views.ss_logout, name='ss-logout'),
]

bt_patterns = [
    # display payment form (for testing only)
    url(r'^test-form/?$', payment_views.TestForm.as_view(), name='bt-test-form'),
    url(r'^test-form-checkout/?$', payment_views.TestFormCheckout.as_view(), name='bt-test-form-checkout'),
]

ac_patterns = [
    url(r'^useremail-autocomplete/$', ac_views.UserEmailAutocomplete.as_view(), name='useremail-autocomplete'),
    url(r'^statename-autocomplete/$', ac_views.StateNameAutocomplete.as_view(), name='statename-autocomplete'),
]

api_patterns = [
    # ping test
    url(r'^ping/?$', views.PingTest.as_view(), name='ping-pong'),

    # AUTH
    url(r'^auth/status/?$', auth_views.auth_status, name='get-auth-status'),
    # client gets access token and exchanges it for internal token, and login user
    url(r'^auth/login/(?P<access_token>[^/]+)/?$', auth_views.login_via_token, name='login-via-token'),
    # client requests to revoke internal token and logout user
    url(r'^auth/logout/?$', auth_views.logout_via_token, name='logout-via-token'),

    # BRAINTREE & SHOP
    url(r'^shop/client-token/?$', payment_views.GetToken.as_view(), name='get-client-token'),
    url(r'^shop/client-methods/?$', payment_views.GetPaymentMethods.as_view(), name='shop-client-payment-methods'),
    url(r'^shop/new-subscription/?$', payment_views.NewSubscription.as_view(), name='shop-new-subscription'),
    url(r'^shop/cancel-subscription/?$', payment_views.CancelSubscription.as_view(), name='shop-cancel-subscription'),
    url(r'^shop/resume-subscription/?$', payment_views.ResumeSubscription.as_view(), name='shop-resume-subscription'),
    url(r'^shop/update-token/?$', payment_views.UpdatePaymentToken.as_view(), name='shop-update-token'),
    url(r'^shop/trial-to-active/?$', payment_views.SwitchTrialToActive.as_view(), name='shop-trial-to-active'),
    url(r'^shop/upgrade-plan/?$', payment_views.UpgradePlan.as_view(), name='shop-upgrade-plan'),
    url(r'^shop/upgrade-plan-amount/(?P<plan_pk>[0-9]+)/?$', payment_views.UpgradePlanAmount.as_view(), name='shop-upgrade-plan-amount'),
    url(r'^shop/downgrade-plan/?$', payment_views.DowngradePlan.as_view(), name='shop-downgrade-plan'),
    url(r'^shop/activate-paid-subscription/?$', payment_views.ActivatePaidSubscription.as_view(), name='activate-paid-subscription'),
    url(r'^shop/plans/?$', views.SubscriptionPlanList.as_view(), name='shop-plans'),
    url(r'^shop/plans-public/(?P<landing_key>[a-zA-Z0-9_/\-]+)/?$', views.SubscriptionPlanPublic.as_view(), name='shop-plan-public'),
    url(r'^shop/signup-discounts/?$', views.SignupDiscountList.as_view(), name='shop-signup-discounts'),

    # Account and Profile-related
    url(r'^accounts/?$', views.CustomerList.as_view()),
    url(r'^accounts/(?P<pk>[0-9]+)/?$', views.CustomerDetail.as_view()),
    url(r'^profiles/?$', views.ProfileList.as_view()),
    url(r'^profiles/(?P<pk>[0-9]+)/?$', views.ProfileUpdate.as_view()),
    url(r'^profiles/verify-email/?$', views.VerifyProfileEmail.as_view(), name='profile-verify-email'),
    url(r'^profiles/set-accessed-tour/?$', views.SetProfileAccessedTour.as_view(), name='profile-set-accessed-tour'),
    url(r'^profiles/set-cmetags/?$', views.ManageProfileCmetags.as_view(), name='profile-set-cmetags'),
    url(r'^cmetags/?$', views.CmeTagList.as_view()),
    #url(r'^cmetags/(?P<pk>[0-9]+)/?$', views.CmeTagDetail.as_view()),
    url(r'^degrees/?$', views.DegreeList.as_view()),
    #url(r'^degrees/(?P<pk>[0-9]+)/?$', views.DegreeDetail.as_view()),
    url(r'^countries/?$', views.CountryList.as_view()),
    #url(r'^countries/(?P<pk>[0-9]+)/?$', views.CountryDetail.as_view()),
    url(r'^hospitals/?$', views.HospitalList.as_view()),
    url(r'^practice-specialties/?$', views.PracticeSpecialtyList.as_view()),
    #url(r'^practice-specialties/(?P<pk>[0-9]+)/?$', views.PracticeSpecialtyDetail.as_view()),
    url(r'^residency-programs/?$', views.ResidencyProgramList.as_view()),
    url(r'^user-state-licenses/?$', views.UserStateLicenseList.as_view()),
    url(r'^user-state-licenses/(?P<pk>[0-9]+)/?$', views.UserStateLicenseDetail.as_view()),
    url(r'^invite-lookup/(?P<inviteid>[0-9A-Za-z!@]+)/?$', views.InviteIdLookup.as_view()),
    url(r'^aff-lookup/(?P<affid>[0-9A-Za-z]+)/?$', views.AffiliateIdLookup.as_view()),

    # Feed entry types, sponsors, eligibleSites for browserCme
    url(r'^entrytypes/?$', views.EntryTypeList.as_view()),
    #url(r'^entrytypes/(?P<pk>[0-9]+)/?$', views.EntryTypeDetail.as_view()),
    url(r'^sponsors/?$', views.SponsorList.as_view()),
    #url(r'^sponsors/(?P<pk>[0-9]+)/?$', views.SponsorDetail.as_view()),
    url(r'^eligible-sites/?$', views.EligibleSiteList.as_view()),
    url(r'^eligible-sites/(?P<pk>[0-9]+)/?$', views.EligibleSiteDetail.as_view()),

    # FEED
    url(r'^feed/?$', views.FeedList.as_view()),
    url(r'^feed/(?P<pk>[0-9]+)/?$', views.FeedEntryDetail.as_view()),
    url(r'^feed/invalidate-entry/(?P<pk>[0-9]+)/?$', views.InvalidateEntry.as_view()),
    url(r'^feed/invalidate-offer/(?P<pk>[0-9]+)/?$', views.InvalidateOffer.as_view()),
    url(r'^feed/browser-cme-offers/?$', views.OrbitCmeOfferList.as_view()),
    url(r'^feed/browser-cme/?$', views.CreateBrowserCme.as_view()),
    url(r'^feed/browser-cme/(?P<pk>[0-9]+)/?$', views.UpdateBrowserCme.as_view()),
    url(r'^feed/cme/?$', views.CreateSRCme.as_view()),
    url(r'^feed/cme/(?P<pk>[0-9]+)/?$', views.UpdateSRCme.as_view()),
    url(r'^feed/upload-document/?$', views.CreateDocument.as_view()),
    url(r'^feed/delete-document/?$', views.DeleteDocument.as_view()),

    # story
    url(r'^story/?$', views.StoryDetail.as_view()),
    # user feedback (list/create)
    url(r'^feedback/?$', views.UserFeedbackList.as_view()),
    # dashboard
    url(r'^dashboard/cme-aggregate/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', views.CmeAggregateStats.as_view()),
    url(r'^dashboard/cme-certificate/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', views.CreateCmeCertificatePdf.as_view()),
    url(r'^dashboard/cme-specialty-certificate/(?P<start>[0-9]+)/(?P<end>[0-9]+)/(?P<tag_id>[0-9]+)/?$', views.CreateSpecialtyCmeCertificatePdf.as_view()),
    url(r'^dashboard/story-certificate/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', views.CreateStoryCmeCertificatePdf.as_view()),
    url(r'^dashboard/cme-certificate/(?P<referenceId>\w+)/?$', views.AccessCmeCertificate.as_view()),
    url(r'^dashboard/audit-report/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', views.CreateAuditReport.as_view()),
    url(r'^dashboard/audit-report/(?P<referenceId>\w+)/?$', views.AccessAuditReport.as_view()),
    url(r'^dashboard/access-document/(?P<referenceId>\w+)/?$', views.AccessDocumentOrCert.as_view()),

    # ADMIN views to see other users data
    url(r'^admin/users/?$', admin_views.UserList.as_view()),
    url(r'^admin/users/(?P<pk>[0-9]+)/?$', admin_views.UserDetail.as_view()),
    # un-redeemed offers for user (redeemed appear in feed)
    url(r'^admin/offers-for-user/(?P<pk>[0-9]+)/?$', admin_views.UserOfferList.as_view()),
    url(r'^admin/feed-for-user/(?P<pk>[0-9]+)/?$', admin_views.UserFeedList.as_view()),
]
if settings.ENV_TYPE != settings.ENV_PROD:
    # debug
    api_patterns.extend([
        url(r'^debug/make-offer/?$', debug_views.MakeOrbitCmeOffer.as_view()),
        url(r'^debug/make-pinned-message/?$', debug_views.MakePinnedMessage.as_view()),
        url(r'^debug/feed/notification/?$', debug_views.MakeNotification.as_view()),
        url(r'^debug/feed/storycme/?$', debug_views.MakeStoryCme.as_view()),
        url(r'^debug/email-receipt/?$', debug_views.EmailSubscriptionReceipt.as_view()),
        url(r'^debug/email-payment-failure/?$', debug_views.EmailSubscriptionPaymentFailure.as_view()),
        url(r'^debug/invitation-discount/?$', debug_views.InvitationDiscountList.as_view()),
        url(r'^debug/premail/?$', debug_views.PreEmail.as_view()),
        url(r'^debug/email-card-expired/?$', debug_views.EmailCardExpired.as_view()),
        url(r'^debug/email-subs-renewal-reminder/?$', debug_views.EmailSubscriptionRenewalReminder.as_view()),
        url(r'^debug/email-subs-cancel-reminder/?$', debug_views.EmailSubscriptionCancelReminder.as_view()),
    ])


# Custom view to render Swagger UI consuming only /api/ endpoints
@api_view()
@authentication_classes((SessionAuthentication,))
@renderer_classes([CoreJSONRenderer, OpenAPIRenderer, SwaggerCustomUIRenderer])
@permission_classes((IsAuthenticated,))
def swagger_view(request):
    patterns = url(r'^api/v1/', include(api_patterns)),
    generator = schemas.SchemaGenerator(title='Orbit API', patterns=patterns)
    return response.Response(generator.get_schema())


urlpatterns = [
    # api
    url(r'^api/v1/', include(api_patterns)),
    url(r'^ac/', include(ac_patterns)),
    # Django admin interface
    url(r'^admin/', admin_site.urls),
    # Swagger
    url(r'^api-docs/', swagger_view, name='api-docs'),
    # server-side login
    url(r'auth/', include(auth_patterns)),
]
if settings.ENV_TYPE != settings.ENV_PROD:
    urlpatterns.extend([
        # direct use of oauth2_provider. Used for testing
        url(r'^o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
        # BT tests
        url(r'^bt/', include(bt_patterns)),
    ])
