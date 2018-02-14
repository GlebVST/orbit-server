from django import forms
from django.contrib import admin
from django.db.models import Count
from pagedown.widgets import AdminPagedownWidget
from dal import autocomplete
from dal_admin_filters import AutocompleteFilter
from .models import *

class UserFilter(AutocompleteFilter):
    title = 'User'
    field_name = 'user'
    autocomplete_url = 'useremail-autocomplete'


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
    list_display = ('id', 'name', 'formatTags', 'created')
    filter_horizontal = ('cmeTags',)

    def get_queryset(self, request):
        qs = super(PracticeSpecialtyAdmin, self).get_queryset(request)
        return qs.prefetch_related('cmeTags')

class OrgAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'created')

class CmeTagAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'priority', 'description', 'created')

class CountryAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'created')

class StateAdmin(admin.ModelAdmin):
    list_display = ('id', 'country', 'name', 'abbrev', 'rnCertValid', 'created')
    list_filter = ('rnCertValid',)

class ProfileCmetagInline(admin.TabularInline):
    model = ProfileCmetag

class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'firstName', 'lastName', 'formatDegrees', 'verified', 'npiNumber', 'nbcrnaId', 'formatSpecialties', 'modified')
    list_filter = ('verified','npiType')
    search_fields = ['npiNumber', 'lastName']
    filter_horizontal = ('specialties',)
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
    list_display = ('id', 'user', 'state', 'license_type', 'license_no', 'expiryDate', 'created')
    list_select_related = True

class SponsorAdmin(admin.ModelAdmin):
    list_display = ('id', 'abbrev', 'name', 'url', 'logo_url', 'modified')


class OfferTagInline(admin.TabularInline):
    model = OfferCmeTag

class BrowserCmeOfferAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'activityDateLocalTz', 'redeemed', 'url', 'suggestedDescr', 'valid', 'modified')
    #list_display = ('id', 'user', 'activityDate', 'redeemed', 'url', 'formatSuggestedTags', 'modified')
    list_select_related = ('user','eligible_site')
    ordering = ('-modified',)
    inlines = [
        OfferTagInline,
    ]
    list_filter = ('redeemed','valid', UserFilter, 'eligible_site')

    class Media:
        pass


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
    #list_display = ('id', 'domain_name', 'domain_title', 'example_url', 'is_valid_expurl', 'needs_ad_block', 'modified')
    list_display = ('id', 'domain_name', 'domain_title', 'page_title_suffix', 'needs_ad_block', 'is_unlisted', 'modified')
    list_filter = ('is_valid_expurl', 'needs_ad_block', 'all_specialties', 'is_unlisted')
    ordering = ('domain_name',)
    filter_horizontal = ('specialties',)

class PinnedMessageForm(forms.ModelForm):
    title = forms.CharField(widget=forms.TextInput(attrs={'size': 80}))
    #description = forms.CharField(widget=forms.Textarea(attrs={'cols': 80, 'rows': 5}))
    description = forms.CharField(widget=AdminPagedownWidget())

class PinnedMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'startDate', 'expireDate', 'sponsor')
    list_select_related = ('user',)
    date_hierarchy = 'startDate'
    ordering = ('-created',)
    form = PinnedMessageForm

class StoryForm(forms.ModelForm):
    description = forms.CharField(widget=AdminPagedownWidget())

    def clean(self):
        """Check that startDate is earlier than endDate"""
        cleaned_data = super(StoryForm, self).clean()
        startdate = cleaned_data.get('startDate')
        enddate = cleaned_data.get('endDate')
        if startdate and enddate and (startdate >= enddate):
            self.add_error('startDate', 'StartDate must be prior to EndDate')

class StoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'startDate', 'expireDate', 'title', 'launch_url')
    date_hierarchy = 'startDate'
    ordering = ('-startDate',)
    form = StoryForm

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


class InvitationDiscountAdmin(admin.ModelAdmin):
    list_display = ('invitee', 'inviteeDiscount', 'inviter', 'inviterDiscount', 'inviterBillingCycle', 'creditEarned', 'created')
    list_select_related = True
    list_filter = ('creditEarned',)
    ordering = ('-created',)


class SubscriptionPlanKeyAdmin(admin.ModelAdmin):
    list_display = ('id','name','degree','specialty','description','created')
    list_select_related = True
    list_filter = ('degree','specialty')
    ordering = ('-created',)

class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('id',
        'plan_key',
        'planId',
        'name',
        'price',
        'monthlyPrice',
        'discountPrice',
        'discountMonthlyPrice',
        'upgrade_plan',
        'trialDays',
        'modified'
    )
    list_select_related = True
    list_filter = ('active', 'plan_key',)
    ordering = ('-created',)
    fieldsets = (
        (None, {
            'fields': ('plan_key','name','planId','upgrade_plan','downgrade_plan'),
        }),
        ('Price', {
            'fields': ('price', 'discountPrice')
        }),
        ('CME', {
            'fields': ('maxCmeWeek','maxCmeMonth','maxCmeYear')
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
    list_filter = ('status', 'display_status', 'plan')
    ordering = ('-modified',)

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

#
# plugin models
#
class AllowedHostAdmin(admin.ModelAdmin):
    list_display = ('id', 'hostname', 'description', 'has_paywall', 'allow_page_download', 'accept_query_keys', 'created')
    ordering = ('hostname',)

class HostPatternAdmin(admin.ModelAdmin):
    list_display = ('id', 'host', 'eligible_site', 'pattern_key', 'path_contains', 'path_reject')
    list_select_related = ('host','eligible_site')
    list_filter = ('host', 'eligible_site')

class AllowedUrlAdmin(admin.ModelAdmin):
    list_display = ('id', 'eligible_site', 'url', 'valid', 'set_id', 'modified')
    list_select_related = ('host', 'eligible_site')
    list_filter = ('valid','host',)
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
    num_users.short_description = 'Number of users who requested it'
    num_users.admin_order_field = 'num_users'


# http://stackoverflow.com/questions/32612400/auto-register-django-auth-models-using-custom-admin-site
class MyAdminSite(admin.AdminSite):
    site_header = "Orbit Site administration"
    site_url = None

    def __init__(self, *args, **kwargs):
        super(MyAdminSite, self).__init__(*args, **kwargs)
        self._registry.update(admin.site._registry)

admin_site = MyAdminSite()
# register models
admin_site.register(Affiliate, AffiliateAdmin)
admin_site.register(AffiliateDetail, AffiliateDetailAdmin)
admin_site.register(AffiliatePayout, AffiliatePayoutAdmin)
admin_site.register(AuthImpersonation, AuthImpersonationAdmin)
admin_site.register(AuditReport, AuditReportAdmin)
admin_site.register(BatchPayout, BatchPayoutAdmin)
admin_site.register(BrowserCmeOffer, BrowserCmeOfferAdmin)
admin_site.register(Certificate, CertificateAdmin)
admin_site.register(CmeTag, CmeTagAdmin)
admin_site.register(Country, CountryAdmin)
admin_site.register(Customer, CustomerAdmin)
admin_site.register(Degree, DegreeAdmin)
admin_site.register(Discount, DiscountAdmin)
admin_site.register(SignupDiscount, SignupDiscountAdmin)
admin_site.register(Document, DocumentAdmin)
admin_site.register(EligibleSite, EligibleSiteAdmin)
admin_site.register(Entry, EntryAdmin)
admin_site.register(EntryType, EntryTypeAdmin)
admin_site.register(InvitationDiscount, InvitationDiscountAdmin)
admin_site.register(LicenseType, LicenseTypeAdmin)
admin_site.register(Organization, OrgAdmin)
admin_site.register(PinnedMessage, PinnedMessageAdmin)
admin_site.register(Profile, ProfileAdmin)
admin_site.register(PracticeSpecialty, PracticeSpecialtyAdmin)
admin_site.register(Sponsor, SponsorAdmin)
admin_site.register(State, StateAdmin)
admin_site.register(StateLicense, StateLicenseAdmin)
admin_site.register(Story, StoryAdmin)
admin_site.register(UserFeedback, UserFeedbackAdmin)
admin_site.register(SubscriptionPlan, SubscriptionPlanAdmin)
admin_site.register(SubscriptionPlanKey, SubscriptionPlanKeyAdmin)
admin_site.register(UserSubscription, UserSubscriptionAdmin)
admin_site.register(SubscriptionEmail, SubscriptionEmailAdmin)
admin_site.register(SubscriptionTransaction, SubscriptionTransactionAdmin)
#
# plugin models
#
admin_site.register(AllowedHost, AllowedHostAdmin)
admin_site.register(HostPattern, HostPatternAdmin)
admin_site.register(AllowedUrl, AllowedUrlAdmin)
admin_site.register(RejectedUrl, RejectedUrlAdmin)
admin_site.register(RequestedUrl, RequestedUrlAdmin)
