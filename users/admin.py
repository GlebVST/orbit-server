# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django import forms
from django.contrib import admin
from django.db.models import Count
from django.utils import timezone
from dal import autocomplete
from mysite.admin import admin_site
from common.ac_filters import UserFilter, StateFilter
from common.dateutils import fmtLocalDatetime
from .models import *
from django.utils.html import format_html
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.conf.urls import url
from django.contrib import messages
from users.csv_tools import ProviderCsvImport
from cStringIO import StringIO

class AuthImpersonationForm(forms.ModelForm):
    class Meta:
        model = AuthImpersonation
        fields = ('__all__')
        widgets = {
            'impersonatee': autocomplete.ModelSelect2(
                url='useremail-autocomplete',
                attrs={
                    'data-minimum-input-length': 2
                }
            )
        }

class AuthImpersonationAdmin(admin.ModelAdmin):
    list_display = ('id', 'impersonator', 'impersonatee', 'valid', 'expireDate')
    form = AuthImpersonationForm

class DegreeAdmin(admin.ModelAdmin):
    list_display = ('id', 'abbrev', 'name', 'sort_order', 'created')


class PracticeSpecialtyAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'formatTags', 'formatSubSpecialties')
    filter_horizontal = ('cmeTags',)

    def get_queryset(self, request):
        qs = super(PracticeSpecialtyAdmin, self).get_queryset(request)
        return qs.prefetch_related('cmeTags', 'subspecialties')

class SubSpecialtyAdmin(admin.ModelAdmin):
    list_display = ('id', 'specialty', 'name', 'formatTags')
    filter_horizontal = ('cmeTags',)
    list_select_related = True
    list_filter = ('specialty',)

    def get_queryset(self, request):
        qs = super(SubSpecialtyAdmin, self).get_queryset(request)
        return qs.prefetch_related('cmeTags')


class OrgForm(forms.ModelForm):
    class Meta:
        model = Organization
        exclude = (
            'joinCode',
            'credits',
            'providerStat',
            'created',
            'modified'
        )

    def save(self, commit=True):
        """Auto assign joinCode based on code"""
        m = super(OrgForm, self).save(commit=False)
        m.joinCode = m.code.replace(' ', '').lower()
        if not m.creditStartDate:
            m.creditStartDate = timezone.now()
        m.save()
        return m

class OrgGroupInline(admin.TabularInline):
    model = OrgGroup

class OrgAdmin(admin.ModelAdmin):
    list_display = ('id', 'joinCode', 'code', 'name', 'credits', 'creditStartDate')
    form = OrgForm
    ordering = ('joinCode',)
    inlines = [
        OrgGroupInline,
    ]

class OrgFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'user', 'name', 'document', 'csvfile', 'created', 'orgfile_actions')
    readonly_fields = ('orgfile_actions',)
    list_select_related = True
    ordering = ('-created',)

    def get_urls(self):
        urls = super(OrgFileAdmin, self).get_urls()
        custom_urls = [
            url(
                r'^(?P<id>.+)/process/$',
                self.admin_site.admin_view(self.orgfile_process),
                name='orgfile-process',
            ),
        ]
        return custom_urls + urls

    def orgfile_actions(self, obj):
        return format_html(
            '<a class="button" href="{}">Run import</a>',
            reverse('admin:orgfile-process', args=[obj.pk]),
        )
    orgfile_actions.short_description = 'Account Actions'
    orgfile_actions.allow_tags = True

    def orgfile_process(self,  request, id, *args, **kwargs):
        orgfile = self.get_object(request, id)
        org = orgfile.organization
        src_file = orgfile.csvfile if orgfile.csvfile else orgfile.document
        output = StringIO()
        csv = ProviderCsvImport(stdout=output)
        success = csv.processOrgFile(org.id, src_file)
        if success:
            self.message_user(request, 'Success')
        else:
            self.message_user(request, output.getvalue(), messages.WARNING)
        url = reverse(
            'admin:users_orgfile_change',
            args=[orgfile.pk],
            current_app=self.admin_site.name,
        )
        return HttpResponseRedirect(url)

class OrgMemberAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'group', 'user', 'fullname', 'compliance', 'is_admin', 'created', 'pending', 'removeDate')
    list_select_related = True
    list_filter = ('is_admin', 'pending', 'setPasswordEmailSent', 'organization', UserFilter)
    raw_id_fields = ('orgfiles',)
    ordering = ('-created','fullname')

    class Media:
        pass

class CmeTagAdmin(admin.ModelAdmin):
    list_display = ('id', 'priority', 'name', 'description', 'srcme_only', 'instructions')
    list_filter = ('srcme_only',)

class CountryAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'created')

class StateAdmin(admin.ModelAdmin):
    list_display = ('id', 'country', 'name', 'abbrev', 'rnCertValid', 'formatTags', 'formatDEATags', 'formatDOTags')
    list_filter = ('rnCertValid',)
    filter_horizontal = ('cmeTags', 'deaTags', 'doTags')

    def get_queryset(self, request):
        qs = super(StateAdmin, self).get_queryset(request)
        return qs.prefetch_related('cmeTags', 'deaTags')


class HospitalAdmin(admin.ModelAdmin):
    list_display = ('id','state','display_name','city','hasResidencyProgram')
    list_filter = ('hasResidencyProgram', StateFilter)
    list_select_related = ('state',)

    class Media:
        pass


class ProfileCmetagInline(admin.TabularInline):
    model = ProfileCmetag

class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'firstName',
        'lastName',
        'formatDegrees',
        'organization',
        'verified',
        'npiNumber',
        'planId',
        'formatSpecialties',
    )
    list_select_related = ('organization',)
    list_filter = ('verified','npiType', 'organization')
    search_fields = ['npiNumber', 'lastName']
    filter_horizontal = (
        'specialties',
        'subspecialties',
        'hospitals',
        'states'
    )
    inlines = [
        ProfileCmetagInline,
    ]

    def get_queryset(self, request):
        qs = super(ProfileAdmin, self).get_queryset(request)
        return qs.prefetch_related('degrees', 'specialties')

class CustomerAdmin(admin.ModelAdmin):
    list_display = ('user', 'customerId', 'balance', 'modified')
    search_fields = ['customerId',]

class AffiliateAdmin(admin.ModelAdmin):
    list_display = ('user', 'displayLabel', 'paymentEmail', 'bonus', 'modified')
    ordering = ('displayLabel',)

class AffiliateDetailAdmin(admin.ModelAdmin):
    list_display = ('affiliateId', 'affiliate', 'redirect_page', 'jobDescription', 'photoUrl', 'modified')
    ordering = ('affiliate','affiliateId')


class LicenseTypeAdmin(admin.ModelAdmin):
    list_display = ('id','name','created')

class StateLicenseAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'state', 'licenseType', 'licenseNumber', 'expireDate', 'created')
    list_select_related = True
    list_filter = ('licenseType', StateFilter, UserFilter)
    ordering = ('-expireDate','user')

    class Media:
        pass

class SponsorAdmin(admin.ModelAdmin):
    list_display = ('id', 'abbrev', 'name', 'url', 'logo_url', 'modified')


class CreditTypeAdmin(admin.ModelAdmin):
    list_display = ('abbrev', 'name', 'auditname', 'sort_order', 'formatDegrees')
    filter_horizontal = ('degrees',)

    def get_queryset(self, request):
        qs = super(CreditTypeAdmin, self).get_queryset(request)
        return qs.prefetch_related('degrees')

class EntryTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created')

class DocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'content_type','document','md5sum', 'image_h','image_w', 'is_thumb', 'is_certificate', 'set_id', 'created')
    list_select_related = ('user',)

class EntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'entryType', 'activityDate', 'valid', 'description', 'created')
    list_filter = ('entryType', 'valid', UserFilter)
    list_select_related = ('user',)
    raw_id_fields = ('documents',)
    ordering = ('-created',)
    filter_horizontal = ('tags',)

    class Media:
        pass


class EligibleSiteAdmin(admin.ModelAdmin):
    list_display = ('id', 'domain_name', 'domain_title', 'page_title_suffix', 'needs_ad_block', 'issn', 'electronic_issn')
    list_filter = ('needs_ad_block', 'all_specialties', 'is_unlisted', 'verify_journal')
    ordering = ('domain_name',)
    filter_horizontal = ('specialties',)


class UserFeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'hasBias', 'hasUnfairContent', 'message_snippet', 'reviewed', 'created')
    list_filter = ('reviewed', 'hasBias', 'hasUnfairContent', UserFilter)
    ordering = ('-created',)
    actions = ['mark_reviewed', 'clear_reviewed',]

    def mark_reviewed(self, request, queryset):
        rows_updated = queryset.update(reviewed=True)
        self.message_user(request, "Number of rows updated: %s" % rows_updated)
    mark_reviewed.short_description = "Mark selected rows as reviewed"

    def clear_reviewed(self, request, queryset):
        rows_updated = queryset.update(reviewed=False)
        self.message_user(request, "Number of rows updated: %s" % rows_updated)
    clear_reviewed.short_description = "Clear reviewed flag of selected rows"

    class Media:
        pass


class DiscountAdmin(admin.ModelAdmin):
    list_display = ('id','discountType', 'activeForType', 'discountId','name','amount','numBillingCycles','created')
    ordering = ('discountType', '-created',)

class SignupDiscountAdmin(admin.ModelAdmin):
    list_display = ('id','organization','email_domain','discount','expireDate')
    ordering = ('organization','expireDate')

class SignupEmailPromoForm(forms.ModelForm):

    class Meta:
        model = SignupEmailPromo
        exclude = (
            'created',
            'modified'
        )

    def clean_email(self):
        self.cleaned_data['email'] = self.cleaned_data['email'].lower()
        return self.cleaned_data['email']

    def clean(self):
        cleaned_data = super(SignupEmailPromoForm, self).clean()
        v = cleaned_data['email']
        if v and SignupEmailPromo.objects.filter(email=v).exists():
            self.add_error('email', 'Case-insensitive email address already exists for this email.')

class SignupEmailPromoAdmin(admin.ModelAdmin):
    list_display = ('id','email','first_year_price','display_label', 'created')
    ordering = ('email',)
    form = SignupEmailPromoForm

class InvitationDiscountAdmin(admin.ModelAdmin):
    list_display = ('invitee', 'inviteeDiscount', 'inviter', 'inviterDiscount', 'inviterBillingCycle', 'creditEarned', 'created')
    list_select_related = True
    list_filter = ('creditEarned',)
    ordering = ('-created',)


class SubscriptionPlanTypeAdmin(admin.ModelAdmin):
    list_display = ('id','name', 'needs_payment_method')

class SubscriptionPlanKeyAdmin(admin.ModelAdmin):
    list_display = ('id','name','degree','specialty','description','use_free_plan', 'created')
    list_select_related = True
    list_filter = ('use_free_plan', 'degree','specialty')
    ordering = ('-created',)

class PlanForm(forms.ModelForm):

    class Meta:
        model = SubscriptionPlan
        exclude = (
            'planId',
            'created',
            'modified'
        )

    def clean(self):
        """Validation checks
        1. If given, check that maxCmeMonth < maxCmeYear
        2. If plan_type is Enterprise, then Org should be selected
        3. If Organization is selected, then plan_type should be Enterprise
        and Org should only be assigned to 1 active plan at any time.
        """
        cleaned_data = super(PlanForm, self).clean()
        maxCmeMonth = cleaned_data.get('maxCmeMonth')
        maxCmeYear = cleaned_data.get('maxCmeYear')
        plan_type = cleaned_data.get('plan_type')
        org = cleaned_data.get('organization')
        if maxCmeYear and maxCmeMonth and (maxCmeMonth >= maxCmeYear):
            self.add_error('maxCmeMonth', 'maxCmeMonth must be strictly less than maxCmeYear.')
        if maxCmeYear == 0 and maxCmeMonth != 0:
            self.add_error('maxCmeMonth', 'If maxCmeYear=0, then maxCmeMonth must also be 0 (for unlimited CME).')
        pt = SubscriptionPlanType.objects.get(name=SubscriptionPlanType.ENTERPRISE)
        if plan_type == pt and org is None:
            self.add_error('organization', 'Organization must be selected for Enterprise plan_type')
        if org is not None:
            # check plan_type
            if plan_type != pt:
                self.add_error('plan_type', 'If Organization is selected, then plan_type must be Enterprise.')
            # check that org is assigned to only 1 active plan
            qs = SubscriptionPlan.objects.filter(organization=org, active=True)
            if qs.exists():
                p = qs[0]
                self.add_error('organization', 'This Organization is already assigned to active plan: {0}.'.format(p))

    def save(self, commit=True):
        """Auto assign planId based on plan name and hashid of next id"""
        m = super(PlanForm, self).save(commit=False)
        if not m.planId:
            m.planId = SubscriptionPlan.objects.makePlanId(m.name)
        m.save()
        return m

class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('id',
        'plan_type',
        'plan_key',
        'planId',
        'name',
        'display_name',
        'price',
        'monthlyPrice',
        'organization',
        'maxCmeYear',
        'billingCycleMonths',
        'maxCmeMonth'
    )
    list_select_related = True
    list_filter = ('active', 'plan_type', 'plan_key',)
    ordering = ('plan_type', 'plan_key__name','price')
    form = PlanForm
    fieldsets = (
        (None, {
            'fields': ('plan_type', 'organization', 'plan_key','name','display_name', 'upgrade_plan','downgrade_plan'),
        }),
        ('Price', {
            'fields': ('price', 'discountPrice')
        }),
        ('CME', {
            'fields': ('maxCmeYear','maxCmeMonth',)
        }),
        ('Other', {
            'fields': ('trialDays','billingCycleMonths','active',)
        })
    )

class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'subscriptionId', 'user', 'plan', 'status', 'display_status',
        'billingFirstDate', 'billingStartDate', 'billingEndDate', 'billingCycle', 'nextBillingAmount',
        'modified')
    list_select_related = ('user','plan')
    list_filter = ('status', 'display_status', 'plan', UserFilter)
    ordering = ('-modified',)

    class Media:
        pass


class SubscriptionEmailAdmin(admin.ModelAdmin):
    list_display = ('id', 'subscription', 'billingCycle', 'remind_renew_sent', 'expire_alert_sent')
    list_select_related = ('subscription',)
    ordering = ('-modified',)

class SubscriptionTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'transactionId', 'subscription', 'trans_type', 'amount', 'status', 'card_type', 'card_last4', 'receipt_sent', 'created', 'modified')
    list_select_related = ('subscription',)
    raw_id_fields = ('subscription',)
    list_filter = ('receipt_sent',)
    ordering = ('-modified',)


class CertificateAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'referenceId', 'tag','name', 'startDate', 'endDate', 'credits', 'created')
    list_select_related = ('user',)
    search_fields = ['referenceId',]
    list_filter = (UserFilter, 'tag')
    ordering = ('-created',)

    class Media:
        pass

class AuditReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'referenceId', 'name', 'startDate', 'endDate', 'created')
    list_select_related = ('user',)
    list_filter = (UserFilter,)
    search_fields = ['referenceId',]
    ordering = ('-created',)

    class Media:
        pass


class BatchPayoutAdmin(admin.ModelAdmin):
    list_display = ('id','sender_batch_id','payout_batch_id','status','amount','date_completed','modified')
    list_filter = ('status',)
    ordering = ('-modified',)

class AffiliatePayoutAdmin(admin.ModelAdmin):
    list_display = ('convertee','affiliate','status','payoutItemId','transactionId','amount','modified')
    list_select_related = True
    list_filter = ('status',)
    ordering = ('-modified',)

class CmeBoostAdmin(admin.ModelAdmin):
    list_display = ('id','name','credits','price','active','created')
    list_filter = ('active',)
    ordering = ('id',)

class CmeBoostPurchaseAdmin(admin.ModelAdmin):
    list_display = ('id','trans_type', 'user','boost','transactionId','amount','status','receipt_sent','created')
    list_filter = ('receipt_sent','failure_alert_sent', 'boost')
    ordering = ('-modified',)

#
# plugin models
#
class AllowedHostAdmin(admin.ModelAdmin):
    list_display = ('id', 'hostname', 'is_secure', 'description', 'has_paywall', 'allow_page_download', 'accept_query_keys', 'created')
    ordering = ('hostname',)
    list_filter = ('is_secure',)

class HostPatternAdmin(admin.ModelAdmin):
    list_display = ('id', 'host', 'eligible_site', 'pattern_key', 'path_contains', 'path_reject')
    list_select_related = ('host','eligible_site')
    list_filter = ('host', 'eligible_site')

class AllowedUrlAdmin(admin.ModelAdmin):
    list_display = ('id', 'eligible_site', 'url', 'valid', 'set_id', 'modified')
    list_select_related = ('host', 'eligible_site')
    list_filter = ('valid','host',)
    filter_horizontal = ('cmeTags',)
    ordering = ('-modified',)

class RejectedUrlAdmin(admin.ModelAdmin):
    list_display = ('id', 'host', 'url', 'created')
    list_select_related = ('host',)
    list_filter = ('host',)
    ordering = ('-created',)

class RequestedUrlAdmin(admin.ModelAdmin):
    list_display = ('id', 'url', 'valid', 'num_users', 'created')
    raw_id_fields = ('users',)
    readonly_fields = ('num_users',)
    ordering = ('-created',)

    def get_queryset(self, request):
        qs = super(RequestedUrlAdmin, self).get_queryset(request)
        return qs.annotate(num_users=Count('users'))

    def num_users(self, obj):
        return obj.num_users
    num_users.short_description = 'Num requesters'
    num_users.admin_order_field = 'num_users'

class ActivitySetAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'url', 'total_tracking_seconds', 'engaged_seconds', 'created')
    raw_id_fields = ('url',)
    readonly_fields = ('user','url','total_tracking_seconds',)
    list_filter = (UserFilter, )
    ordering = ('-created',)

    class Media:
        pass

    def engaged_seconds(self, obj):
        return obj.computed_value
    engaged_seconds.short_description = 'Engaged Seconds'
    engaged_seconds.admin_order_field = 'computed_value'

class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'url', 'x_tracking_seconds', 'num_highlight', 'num_mouse_click', 'num_mouse_move', 'num_start_scroll', 'created')
    raw_id_fields = ('activity_set',)
    readonly_fields = ('activity_set','num_highlight','num_mouse_click','num_mouse_move','num_start_scroll')
    ordering = ('-created',)

    def get_queryset(self, request):
        qs = super(ActivityLogAdmin, self).get_queryset(request)
        return qs.select_related('activity_set')

    def user(self, obj):
        return str(obj.activity_set.user)

    def url(self, obj):
        return str(obj.activity_set.url)

class RecAllowedUrlAdmin(admin.ModelAdmin):
    list_display = ('id','user','cmeTag','url', 'offerid')
    raw_id_fields = ('url', 'offer')
    list_filter = (UserFilter, 'cmeTag')
    ordering = ('cmeTag','user')

    def offerid(self, obj):
        return obj.offer.pk if obj.offer else None

    class Media:
        pass

class OrbitCmeOfferAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'activityDate', 'redeemed', 'url', 'suggestedDescr', 'valid', 'lastModified')
    #list_display = ('id', 'user', 'activityDate', 'redeemed', 'url', 'formatSuggestedTags', 'lastModified')
    list_select_related = True
    ordering = ('-modified',)
    list_filter = ('redeemed','valid', UserFilter, 'eligible_site')

    class Media:
        pass

    def lastModified(self, obj):
        return fmtLocalDatetime(obj.modified)
    lastModified.short_description = 'Last Modified'
    lastModified.admin_order_field = 'modified'

# register models
admin_site.register(Affiliate, AffiliateAdmin)
admin_site.register(AffiliateDetail, AffiliateDetailAdmin)
admin_site.register(AffiliatePayout, AffiliatePayoutAdmin)
admin_site.register(AuthImpersonation, AuthImpersonationAdmin)
admin_site.register(AuditReport, AuditReportAdmin)
admin_site.register(BatchPayout, BatchPayoutAdmin)
admin_site.register(Certificate, CertificateAdmin)
admin_site.register(CmeBoost, CmeBoostAdmin)
admin_site.register(CmeBoostPurchase, CmeBoostPurchaseAdmin)
admin_site.register(CmeTag, CmeTagAdmin)
admin_site.register(Country, CountryAdmin)
admin_site.register(CreditType, CreditTypeAdmin)
admin_site.register(Customer, CustomerAdmin)
admin_site.register(Degree, DegreeAdmin)
admin_site.register(Discount, DiscountAdmin)
admin_site.register(SignupDiscount, SignupDiscountAdmin)
admin_site.register(SignupEmailPromo, SignupEmailPromoAdmin)
admin_site.register(Document, DocumentAdmin)
admin_site.register(EligibleSite, EligibleSiteAdmin)
admin_site.register(Entry, EntryAdmin)
admin_site.register(EntryType, EntryTypeAdmin)
admin_site.register(Hospital, HospitalAdmin)
admin_site.register(InvitationDiscount, InvitationDiscountAdmin)
admin_site.register(LicenseType, LicenseTypeAdmin)
admin_site.register(Organization, OrgAdmin)
admin_site.register(OrgFile, OrgFileAdmin)
admin_site.register(OrgMember, OrgMemberAdmin)
admin_site.register(Profile, ProfileAdmin)
admin_site.register(PracticeSpecialty, PracticeSpecialtyAdmin)
admin_site.register(Sponsor, SponsorAdmin)
admin_site.register(State, StateAdmin)
admin_site.register(StateLicense, StateLicenseAdmin)
admin_site.register(UserFeedback, UserFeedbackAdmin)
admin_site.register(SubscriptionEmail, SubscriptionEmailAdmin)
admin_site.register(SubscriptionPlan, SubscriptionPlanAdmin)
admin_site.register(SubscriptionPlanKey, SubscriptionPlanKeyAdmin)
admin_site.register(SubscriptionPlanType, SubscriptionPlanTypeAdmin)
admin_site.register(SubscriptionTransaction, SubscriptionTransactionAdmin)
admin_site.register(SubSpecialty, SubSpecialtyAdmin)
admin_site.register(UserSubscription, UserSubscriptionAdmin)
#
# plugin models
#
admin_site.register(AllowedHost, AllowedHostAdmin)
admin_site.register(HostPattern, HostPatternAdmin)
admin_site.register(AllowedUrl, AllowedUrlAdmin)
admin_site.register(RejectedUrl, RejectedUrlAdmin)
admin_site.register(RequestedUrl, RequestedUrlAdmin)
admin_site.register(ActivitySet, ActivitySetAdmin)
admin_site.register(ActivityLog, ActivityLogAdmin)
admin_site.register(RecAllowedUrl, RecAllowedUrlAdmin)
admin_site.register(OrbitCmeOffer, OrbitCmeOfferAdmin)
