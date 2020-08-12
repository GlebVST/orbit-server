"""mysite URL Configuration
"""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
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

auth_patterns = [
    # site login via server-side login (for testing only)
    re_path(r'^ss-login/?$', auth_views.ss_login, name='ss-login'),
    re_path(r'^auth0-cb-login/?$', auth_views.login_via_code, name='login-via-code'),
    re_path(r'^ss-login-error/?$', auth_views.ss_login_error, name='ss-login-error'),
    re_path(r'^ss-home/?$', auth_views.ss_home, name='ss-home'),
    re_path(r'^ss-logout/?$', auth_views.ss_logout, name='ss-logout'),
]

bt_patterns = [
    # display payment form (for testing only)
    re_path(r'^test-form/?$', payment_views.TestForm.as_view(), name='bt-test-form'),
    re_path(r'^test-form-checkout/?$', payment_views.TestFormCheckout.as_view(), name='bt-test-form-checkout'),
]

ac_patterns = [
    re_path(r'^useremail-autocomplete/$', ac_views.UserEmailAutocomplete.as_view(), name='useremail-autocomplete'),
    re_path(r'^cmetag-autocomplete/$', ac_views.CmeTagAutocomplete.as_view(), name='cmetag-autocomplete'),
    re_path(r'^statename-autocomplete/$', ac_views.StateNameAutocomplete.as_view(), name='statename-autocomplete'),
    re_path(r'^hospital-autocomplete/$', ac_views.HospitalAutocomplete.as_view(), name='hospital-autocomplete'),
    re_path(r'^are_path-autocomplete/$', ac_views.AllowedUrlAutocomplete.as_view(), name='are_path-autocomplete'),
    re_path(r'^esite-autocomplete/$', ac_views.EligibleSiteAutocomplete.as_view(), name='esite-autocomplete'),
    re_path(r'^specialty-autocomplete/$', ac_views.PracticeSpecialtyAutocomplete.as_view(), name='specialty-autocomplete'),
    re_path(r'^licensegoal-autocomplete/$', goal_ac_views.LicenseGoalAutocomplete.as_view(), name='licensegoal-autocomplete'),
]

api_patterns = [
    # ping test
    re_path(r'^ping/?$', views.PingTest.as_view(), name='ping-pong'),

    # AUTH
    re_path(r'^auth/debug/?$', auth_views.auth_debug, name='auth-debug'),
    re_path(r'^auth/status/?$', auth_views.auth_status, name='auth-status'),
    # new user signup
    re_path(r'^auth/signup/(?P<bt_plan_id>[a-zA-Z0-9_\-]+)/?$', auth_views.signup, name='auth-signup'),
    # client requests to revoke internal token and logout user
    re_path(r'^auth/logout/?$', auth_views.logout, name='auth-logout'),

    # payment views
    re_path(r'^shop/client-token/?$', payment_views.GetToken.as_view(), name='get-client-token'),
    re_path(r'^shop/client-methods/?$', payment_views.GetPaymentMethods.as_view(), name='shop-client-payment-methods'),
    re_path(r'^shop/new-subscription/?$', payment_views.NewSubscription.as_view(), name='shop-new-subscription'),
    re_path(r'^shop/cancel-subscription/?$', payment_views.CancelSubscription.as_view(), name='shop-cancel-subscription'),
    re_path(r'^shop/resume-subscription/?$', payment_views.ResumeSubscription.as_view(), name='shop-resume-subscription'),
    re_path(r'^shop/update-token/?$', payment_views.UpdatePaymentToken.as_view(), name='shop-update-token'),
    re_path(r'^shop/trial-to-active/?$', payment_views.SwitchTrialToActive.as_view(), name='shop-trial-to-active'),
    re_path(r'^shop/upgrade-plan/?$', payment_views.UpgradePlan.as_view(), name='shop-upgrade-plan'),
    re_path(r'^shop/upgrade-plan-amount/(?P<plan_pk>[0-9]+)/?$', payment_views.UpgradePlanAmount.as_view(), name='shop-upgrade-plan-amount'),
    re_path(r'^shop/downgrade-plan/?$', payment_views.DowngradePlan.as_view(), name='shop-downgrade-plan'),
    re_path(r'^shop/activate-paid-subscription/?$', payment_views.ActivatePaidSubscription.as_view(), name='activate-paid-subscription'),
    re_path(r'^shop/plan-welcome-info/?$', payment_views.SubscriptionPlanWelcomeInfo.as_view(), name='shop-plan-welcome-info'),
    re_path(r'^shop/plans/?$', payment_views.SubscriptionPlanList.as_view(), name='shop-plans'),
    re_path(r'^shop/plans-public/(?P<landing_key>[a-zA-Z0-9_/\-]+)/?$', payment_views.SubscriptionPlanPublic.as_view(), name='shop-plan-public'),
    re_path(r'^shop/signup-discounts/?$', payment_views.SignupDiscountList.as_view(), name='shop-signup-discounts'),
    re_path(r'^shop/boosts/?$', payment_views.CmeBoostList.as_view(), name='shop-boosts'),
    re_path(r'^shop/boosts/purchase?$', payment_views.CmeBoostPurchase.as_view(), name='shop-boost-purchase'),

    # views
    re_path(r'^profiles/(?P<pk>[0-9]+)/?$', views.ProfileUpdate.as_view()),
    re_path(r'^profiles/(?P<pk>[0-9]+)/update-initial/?$', views.ProfileInitialUpdate.as_view(), name='profile-initial-update'),
    re_path(r'^profiles/set-email/?$', views.UserEmailUpdate.as_view()),
    re_path(r'^profiles/set-accessed-tour/?$', views.SetProfileAccessedTour.as_view(), name='profile-set-accessed-tour'),
    re_path(r'^profiles/set-cmetags/?$', views.ManageProfileCmetags.as_view(), name='profile-set-cmetags'),
    re_path(r'^cmetags/?$', views.CmeTagList.as_view()),
    re_path(r'^degrees/?$', views.DegreeList.as_view()),
    re_path(r'^countries/?$', views.CountryList.as_view()),
    re_path(r'^hospitals/?$', views.HospitalList.as_view()),
    re_path(r'^license-types/?$', views.LicenseTypeList.as_view()),
    re_path(r'^practice-specialties/?$', views.PracticeSpecialtyList.as_view()),
    re_path(r'^residency-programs/?$', views.ResidencyProgramList.as_view()),
    re_path(r'^licenses/?$', views.UserStateLicenseList.as_view()),
    re_path(r'^invite-lookup/(?P<inviteid>[0-9A-Za-z!@]+)/?$', views.InviteIdLookup.as_view()),
    re_path(r'^aff-lookup/(?P<affid>[0-9A-Za-z]+)/?$', views.AffiliateIdLookup.as_view()),
    re_path(r'^emlkup/?$', views.EmailLookup.as_view()),
    re_path(r'^eligible-sites/?$', views.EligibleSiteList.as_view()),
    re_path(r'^eligible-sites/(?P<pk>[0-9]+)/?$', views.EligibleSiteDetail.as_view()),
    re_path(r'^upload-document/?$', views.CreateDocument.as_view()),
    re_path(r'^delete-document/?$', views.DeleteDocument.as_view()),
    re_path(r'^feedback/?$', views.UserFeedbackList.as_view()),

    # Feed views
    re_path(r'^entrytypes/?$', feed_views.EntryTypeList.as_view()),
    re_path(r'^sponsors/?$', feed_views.SponsorList.as_view()),
    re_path(r'^feed/?$', feed_views.FeedList.as_view()),
    re_path(r'^feed/(?P<pk>[0-9]+)/?$', feed_views.FeedEntryDetail.as_view()),
    re_path(r'^feed/invalidate-entry/(?P<pk>[0-9]+)/?$', feed_views.InvalidateEntry.as_view()),
    re_path(r'^feed/invalidate-offer/(?P<pk>[0-9]+)/?$', feed_views.InvalidateOffer.as_view()),
    re_path(r'^feed/browser-cme-offers/?$', feed_views.OrbitCmeOfferList.as_view()),
    re_path(r'^feed/browser-cme/?$', feed_views.CreateBrowserCme.as_view()),
    re_path(r'^feed/browser-cme/(?P<pk>[0-9]+)/?$', feed_views.UpdateBrowserCme.as_view()),
    re_path(r'^feed/cme/?$', feed_views.CreateSRCme.as_view()),
    re_path(r'^feed/cme/(?P<pk>[0-9]+)/?$', feed_views.UpdateSRCme.as_view()),
    re_path(r'^feed/rec-articles/?$', feed_views.RecAllowedUrlList.as_view()),

    # dashboard
    re_path(r'^dashboard/cme-aggregate/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', dashboard_views.CmeAggregateStats.as_view()),
    re_path(r'^dashboard/cme-certificate/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', dashboard_views.CreateCmeCertificatePdf.as_view()),
    re_path(r'^dashboard/cme-specialty-certificate/(?P<start>[0-9]+)/(?P<end>[0-9]+)/(?P<tag_id>[0-9]+)/?$', dashboard_views.CreateSpecialtyCmeCertificatePdf.as_view()),
    re_path(r'^dashboard/story-certificate/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', dashboard_views.CreateStoryCmeCertificatePdf.as_view()),
    re_path(r'^dashboard/cme-certificate/(?P<referenceId>\w+)/?$', dashboard_views.AccessCmeCertificate.as_view()),
    re_path(r'^dashboard/audit-report/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', dashboard_views.CreateAuditReport.as_view()),
    re_path(r'^dashboard/audit-report/(?P<referenceId>\w+)/?$', dashboard_views.AccessAuditReport.as_view()),
    re_path(r'^dashboard/access-document/(?P<referenceId>\w+)/?$', dashboard_views.AccessDocumentOrCert.as_view()),

    # goals
    re_path(r'^goaltypes/?$', goal_views.GoalTypeList.as_view()),
    re_path(r'^goals/?$', goal_views.UserGoalList.as_view()),
    re_path(r'^goals/create-license/?$', goal_views.CreateUserLicenseGoal.as_view()),
    re_path(r'^goals/update-license/(?P<pk>[0-9]+)/?$', goal_views.UpdateUserLicenseGoal.as_view()),
    re_path(r'^goals/admin-update-license/(?P<pk>[0-9]+)/?$', goal_views.AdminUpdateUserLicenseGoal.as_view()),
    re_path(r'^goals/remove-licenses/?$', goal_views.RemoveUserLicenseGoals.as_view()),
    re_path(r'^goals/user-summary/(?P<userid>[0-9]+)/?$', goal_views.UserGoalSummary.as_view()),
    re_path(r'^goals/recs/(?P<pk>[0-9]+)/?$', goal_views.GoalRecsList.as_view()),

    # enterprise admin
    re_path(r'^enterprise/orggroups/?$', enterprise_views.OrgGroupList.as_view()),
    re_path(r'^enterprise/orggroups/(?P<pk>[0-9]+)/?$', enterprise_views.OrgGroupDetail.as_view()),
    re_path(r'^enterprise/orgmembers/?$', enterprise_views.OrgMemberList.as_view()),
    re_path(r'^enterprise/orgmembers-create/?$', enterprise_views.OrgMemberCreate.as_view()),
    re_path(r'^enterprise/orgmembers/(?P<pk>[0-9]+)/?$', enterprise_views.OrgMemberDetail.as_view()),
    re_path(r'^enterprise/orgmembers/(?P<pk>[0-9]+)/licenses?$', enterprise_views.OrgMemberLicenseList.as_view()),
    re_path(r'^enterprise/orgmembers-update/(?P<pk>[0-9]+)/?$', enterprise_views.OrgMemberUpdate.as_view()),
    re_path(r'^enterprise/orgmembers-remove/?$', enterprise_views.OrgMembersRemove.as_view()),
    re_path(r'^enterprise/orgmembers-email-invite/?$', enterprise_views.OrgMembersEmailInvite.as_view()),
    re_path(r'^enterprise/orgmembers-restore/?$', enterprise_views.OrgMembersRestore.as_view()),
    re_path(r'^enterprise/orgmembers-audit-report/(?P<memberId>[0-9]+)/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', enterprise_views.EnterpriseMemberAuditReport.as_view()),
    re_path(r'^enterprise/orgfiles/?$', enterprise_views.OrgFileList.as_view()),
    re_path(r'^enterprise/upload-roster/?$', enterprise_views.UploadRoster.as_view()),
    re_path(r'^enterprise/upload-license/?$', enterprise_views.UploadLicense.as_view()),
    re_path(r'^enterprise/process-license-file/(?P<pk>[0-9]+)/?$', enterprise_views.ProcessUploadedLicenseFile.as_view()),
    re_path(r'^enterprise/team-stats/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', enterprise_views.TeamStats.as_view()),
    re_path(r'^enterprise/join-team/?$', enterprise_views.JoinTeam.as_view()),
    re_path(r'^enterprise/report/?$', enterprise_views.OrgReportList.as_view(), name='enterprise-report-list'),
    re_path(r'^enterprise/enrollment/?$', enterprise_views.OrgEnrolleeList.as_view(), name='enterprise-enrollee-list'),
    # reports - must specify name for reverse (used as value for OrgReport.resource field)
    re_path(r'^enterprise/report/roster/?$', enterprise_views.OrgMemberRoster.as_view(), name='enterprise-report-roster'),
]
if settings.ENV_TYPE != settings.ENV_PROD:
    # debug
    api_patterns.extend([
        re_path(r'^debug/make-offer/?$', debug_views.MakeOrbitCmeOffer.as_view()),
        re_path(r'^debug/email-receipt/?$', debug_views.EmailSubscriptionReceipt.as_view()),
        re_path(r'^debug/email-payment-failure/?$', debug_views.EmailSubscriptionPaymentFailure.as_view()),
        re_path(r'^debug/invitation-discount/?$', debug_views.InvitationDiscountList.as_view()),
        re_path(r'^debug/premail/?$', debug_views.PreEmail.as_view()),
        re_path(r'^debug/email-card-expired/?$', debug_views.EmailCardExpired.as_view()),
        re_path(r'^debug/email-subs-renewal-reminder/?$', debug_views.EmailSubscriptionRenewalReminder.as_view()),
        re_path(r'^debug/email-subs-cancel-reminder/?$', debug_views.EmailSubscriptionCancelReminder.as_view()),
        re_path(r'^debug/orgmembers/?$', debug_views.OrgMemberList.as_view()),
        re_path(r'^debug/orgmembers/add/?$', debug_views.CreateOrgMember.as_view()),
        re_path(r'^debug/orgmembers/(?P<pk>[0-9]+)/?$', debug_views.OrgMemberDetail.as_view()),
        re_path(r'^debug/orgmembers/(?P<pk>[0-9]+)/update/?$', debug_views.UpdateOrgMember.as_view()),
        re_path(r'^debug/orgmembers/(?P<pk>[0-9]+)/email-set-password/?$', debug_views.EmailSetPassword.as_view()),
        re_path(r'^debug/audit-report/(?P<userid>[0-9]+)/(?P<start>[0-9]+)/(?P<end>[0-9]+)/?$', debug_views.CreateAuditReport.as_view()),
        re_path(r'^debug/validate-license-file/(?P<pk>[0-9]+)/?$', debug_views.ValidateLicenseFile.as_view()),
        re_path(r'^debug/recare_paths-for-user/(?P<userid>[0-9]+)/?$', debug_views.RecAllowedUrlListForUser.as_view()),
        re_path(r'^debug/documents/?$', debug_views.DocumentList.as_view()),
    ])


urlpatterns = [
    # api
    re_path(r'^api/v1/', include(api_patterns)),
    re_path(r'^ac/', include(ac_patterns)),
    # Django admin interface
    re_path(r'^admin/', admin_site.urls),
]
if settings.ENV_TYPE != settings.ENV_PROD:
    urlpatterns.extend([
        # BT tests
        re_path(r'^bt/', include(bt_patterns)),
        # server-side login
        re_path(r'auth/', include(auth_patterns)),
    ])
