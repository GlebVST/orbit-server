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
from .admin import admin_site
from users import (
        ac_views,
        auth_views,
        dashboard_views,
        debug_views,
        feed_views,
        enterprise_views,
        payment_views,
        views
)
from goals import views as goal_views
from goals import ac_views as goal_ac_views
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
    url(r'^cmetag-autocomplete/$', ac_views.CmeTagAutocomplete.as_view(), name='cmetag-autocomplete'),
    url(r'^statename-autocomplete/$', ac_views.StateNameAutocomplete.as_view(), name='statename-autocomplete'),
    url(r'^hospital-autocomplete/$', ac_views.HospitalAutocomplete.as_view(), name='hospital-autocomplete'),
    url(r'^aurl-autocomplete/$', ac_views.AllowedUrlAutocomplete.as_view(), name='aurl-autocomplete'),
    url(r'^esite-autocomplete/$', ac_views.EligibleSiteAutocomplete.as_view(), name='esite-autocomplete'),
    url(r'^specialty-autocomplete/$', ac_views.PracticeSpecialtyAutocomplete.as_view(), name='specialty-autocomplete'),
    url(r'^licensegoal-autocomplete/$', goal_ac_views.LicenseGoalAutocomplete.as_view(), name='licensegoal-autocomplete'),
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

    # payment views
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
    url(r'^shop/plan-welcome-info/?$', payment_views.SubscriptionPlanWelcomeInfo.as_view(), name='shop-plan-welcome-info'),
    url(r'^shop/plans/?$', payment_views.SubscriptionPlanList.as_view(), name='shop-plans'),
    url(r'^shop/plans-public/(?P<landing_key>[a-zA-Z0-9_/\-]+)/?$', payment_views.SubscriptionPlanPublic.as_view(), name='shop-plan-public'),
    url(r'^shop/signup-discounts/?$', payment_views.SignupDiscountList.as_view(), name='shop-signup-discounts'),
    url(r'^shop/boosts/?$', payment_views.CmeBoostList.as_view(), name='shop-boosts'),
    url(r'^shop/boosts/purchase?$', payment_views.CmeBoostPurchase.as_view(), name='shop-boost-purchase'),

    # views
    url(r'^profiles/(?P<pk>[0-9]+)/?$', views.ProfileUpdate.as_view()),
    url(r'^profiles/(?P<pk>[0-9]+)/update-initial/?$', views.ProfileInitialUpdate.as_view(), name='profile-initial-update'),
    url(r'^profiles/set-email/?$', views.UserEmailUpdate.as_view()),
    url(r'^profiles/set-accessed-tour/?$', views.SetProfileAccessedTour.as_view(), name='profile-set-accessed-tour'),
    url(r'^profiles/set-cmetags/?$', views.ManageProfileCmetags.as_view(), name='profile-set-cmetags'),
    url(r'^cmetags/?$', views.CmeTagList.as_view()),
    url(r'^degrees/?$', views.DegreeList.as_view()),
    url(r'^countries/?$', views.CountryList.as_view()),
    url(r'^hospitals/?$', views.HospitalList.as_view()),
    url(r'^license-types/?$', views.LicenseTypeList.as_view()),
    url(r'^practice-specialties/?$', views.PracticeSpecialtyList.as_view()),
    url(r'^residency-programs/?$', views.ResidencyProgramList.as_view()),
    url(r'^licenses/?$', views.UserStateLicenseList.as_view()),
    url(r'^invite-lookup/(?P<inviteid>[0-9A-Za-z!@]+)/?$', views.InviteIdLookup.as_view()),
    url(r'^aff-lookup/(?P<affid>[0-9A-Za-z]+)/?$', views.AffiliateIdLookup.as_view()),
    url(r'^emlkup/?$', views.EmailLookup.as_view()),
    url(r'^eligible-sites/?$', views.EligibleSiteList.as_view()),
    url(r'^eligible-sites/(?P<pk>[0-9]+)/?$', views.EligibleSiteDetail.as_view()),
    url(r'^upload-document/?$', views.CreateDocument.as_view()),
    url(r'^delete-document/?$', views.DeleteDocument.as_view()),
    url(r'^feedback/?$', views.UserFeedbackList.as_view()),

    # Feed views
    url(r'^entrytypes/?$', feed_views.EntryTypeList.as_view()),
    url(r'^sponsors/?$', feed_views.SponsorList.as_view()),
    url(r'^feed/?$', feed_views.FeedList.as_view()),
    url(r'^feed/(?P<pk>[0-9]+)/?$', feed_views.FeedEntryDetail.as_view()),
    url(r'^feed/invalidate-entry/(?P<pk>[0-9]+)/?$', feed_views.InvalidateEntry.as_view()),
    url(r'^feed/invalidate-offer/(?P<pk>[0-9]+)/?$', feed_views.InvalidateOffer.as_view()),
    url(r'^feed/browser-cme-offers/?$', feed_views.OrbitCmeOfferList.as_view()),
    url(r'^feed/browser-cme/?$', feed_views.CreateBrowserCme.as_view()),
    url(r'^feed/browser-cme/(?P<pk>[0-9]+)/?$', feed_views.UpdateBrowserCme.as_view()),
    url(r'^feed/cme/?$', feed_views.CreateSRCme.as_view()),
    url(r'^feed/cme/(?P<pk>[0-9]+)/?$', feed_views.UpdateSRCme.as_view()),
    url(r'^feed/rec-articles/?$', feed_views.RecAllowedUrlList.as_view()),

    # dashboard
    url(r'^dashboard/cme-aggregate/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', dashboard_views.CmeAggregateStats.as_view()),
    url(r'^dashboard/cme-certificate/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', dashboard_views.CreateCmeCertificatePdf.as_view()),
    url(r'^dashboard/cme-specialty-certificate/(?P<start>[0-9]+)/(?P<end>[0-9]+)/(?P<tag_id>[0-9]+)/?$', dashboard_views.CreateSpecialtyCmeCertificatePdf.as_view()),
    url(r'^dashboard/story-certificate/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', dashboard_views.CreateStoryCmeCertificatePdf.as_view()),
    url(r'^dashboard/cme-certificate/(?P<referenceId>\w+)/?$', dashboard_views.AccessCmeCertificate.as_view()),
    url(r'^dashboard/audit-report/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', dashboard_views.CreateAuditReport.as_view()),
    url(r'^dashboard/audit-report/(?P<referenceId>\w+)/?$', dashboard_views.AccessAuditReport.as_view()),
    url(r'^dashboard/access-document/(?P<referenceId>\w+)/?$', dashboard_views.AccessDocumentOrCert.as_view()),

    # goals
    url(r'^goaltypes/?$', goal_views.GoalTypeList.as_view()),
    url(r'^goals/?$', goal_views.UserGoalList.as_view()),
    url(r'^goals/create-license/?$', goal_views.CreateUserLicenseGoal.as_view()),
    url(r'^goals/update-license/(?P<pk>[0-9]+)/?$', goal_views.UpdateUserLicenseGoal.as_view()),
    url(r'^goals/admin-update-license/(?P<pk>[0-9]+)/?$', goal_views.AdminUpdateUserLicenseGoal.as_view()),
    url(r'^goals/remove-licenses/?$', goal_views.RemoveUserLicenseGoals.as_view()),
    url(r'^goals/user-summary/(?P<userid>[0-9]+)/?$', goal_views.UserGoalSummary.as_view()),
    url(r'^goals/recs/(?P<pk>[0-9]+)/?$', goal_views.GoalRecsList.as_view()),

    # enterprise admin
    url(r'^enterprise/orggroups/?$', enterprise_views.OrgGroupList.as_view()),
    url(r'^enterprise/orggroups/(?P<pk>[0-9]+)/?$', enterprise_views.OrgGroupDetail.as_view()),
    url(r'^enterprise/orgmembers/?$', enterprise_views.OrgMemberList.as_view()),
    url(r'^enterprise/orgmembers-create/?$', enterprise_views.OrgMemberCreate.as_view()),
    url(r'^enterprise/orgmembers/(?P<pk>[0-9]+)/?$', enterprise_views.OrgMemberDetail.as_view()),
    url(r'^enterprise/orgmembers/(?P<pk>[0-9]+)/licenses?$', enterprise_views.OrgMemberLicenseList.as_view()),
    url(r'^enterprise/orgmembers-update/(?P<pk>[0-9]+)/?$', enterprise_views.OrgMemberUpdate.as_view()),
    url(r'^enterprise/orgmembers-remove/?$', enterprise_views.OrgMembersRemove.as_view()),
    url(r'^enterprise/orgmembers-email-invite/?$', enterprise_views.OrgMembersEmailInvite.as_view()),
    url(r'^enterprise/orgmembers-restore/?$', enterprise_views.OrgMembersRestore.as_view()),
    url(r'^enterprise/orgmembers-audit-report/(?P<memberId>[0-9]+)/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', enterprise_views.EnterpriseMemberAuditReport.as_view()),
    url(r'^enterprise/orgfiles/?$', enterprise_views.OrgFileList.as_view()),
    url(r'^enterprise/upload-roster/?$', enterprise_views.UploadRoster.as_view()),
    url(r'^enterprise/upload-license/?$', enterprise_views.UploadLicense.as_view()),
    url(r'^enterprise/process-license-file/(?P<pk>[0-9]+)/?$', enterprise_views.ProcessUploadedLicenseFile.as_view()),
    url(r'^enterprise/team-stats/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', enterprise_views.TeamStats.as_view()),
    url(r'^enterprise/join-team/?$', enterprise_views.JoinTeam.as_view()),
    url(r'^enterprise/report/?$', enterprise_views.OrgReportList.as_view(), name='enterprise-report-list'),
    url(r'^enterprise/enrollment/?$', enterprise_views.OrgEnrolleeList.as_view(), name='enterprise-enrollee-list'),
    # reports - must specify name for reverse (used as value for OrgReport.resource field)
    url(r'^enterprise/report/roster/?$', enterprise_views.OrgMemberRoster.as_view(), name='enterprise-report-roster'),
]
if settings.ENV_TYPE != settings.ENV_PROD:
    # debug
    api_patterns.extend([
        url(r'^debug/make-offer/?$', debug_views.MakeOrbitCmeOffer.as_view()),
        url(r'^debug/email-receipt/?$', debug_views.EmailSubscriptionReceipt.as_view()),
        url(r'^debug/email-payment-failure/?$', debug_views.EmailSubscriptionPaymentFailure.as_view()),
        url(r'^debug/invitation-discount/?$', debug_views.InvitationDiscountList.as_view()),
        url(r'^debug/premail/?$', debug_views.PreEmail.as_view()),
        url(r'^debug/email-card-expired/?$', debug_views.EmailCardExpired.as_view()),
        url(r'^debug/email-subs-renewal-reminder/?$', debug_views.EmailSubscriptionRenewalReminder.as_view()),
        url(r'^debug/email-subs-cancel-reminder/?$', debug_views.EmailSubscriptionCancelReminder.as_view()),
        url(r'^debug/orgmembers/?$', debug_views.OrgMemberList.as_view()),
        url(r'^debug/orgmembers/add/?$', debug_views.CreateOrgMember.as_view()),
        url(r'^debug/orgmembers/(?P<pk>[0-9]+)/?$', debug_views.OrgMemberDetail.as_view()),
        url(r'^debug/orgmembers/(?P<pk>[0-9]+)/update/?$', debug_views.UpdateOrgMember.as_view()),
        url(r'^debug/orgmembers/(?P<pk>[0-9]+)/email-set-password/?$', debug_views.EmailSetPassword.as_view()),
        url(r'^debug/audit-report/(?P<userid>[0-9]+)/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', debug_views.CreateAuditReport.as_view()),
        url(r'^debug/validate-license-file/(?P<pk>[0-9]+)/?$', debug_views.ValidateLicenseFile.as_view()),
        url(r'^debug/recaurls-for-user/(?P<userid>[0-9]+)/?$', debug_views.RecAllowedUrlListForUser.as_view()),
        url(r'^debug/documents/?$', debug_views.DocumentList.as_view()),
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
