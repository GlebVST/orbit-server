from django import forms
from django.contrib import admin
from django.db.models import Count
from pagedown.widgets import AdminPagedownWidget
from .models import *

class DegreeAdmin(admin.ModelAdmin):
    list_display = ('id', 'abbrev', 'name', 'created')

class PracticeSpecialtyAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_abms_board', 'formatTags', 'created')
    list_filter = ('is_abms_board',)
    filter_horizontal = ('cmeTags',)

    def get_queryset(self, request):
        qs = super(PracticeSpecialtyAdmin, self).get_queryset(request)
        return qs.prefetch_related('cmeTags')

class CmeTagAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'priority', 'description', 'created')

class CountryAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'created')

class StateAdmin(admin.ModelAdmin):
    list_display = ('id', 'country', 'name', 'abbrev', 'created')

class ProfileCmetagInline(admin.TabularInline):
    model = ProfileCmetag

class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'firstName', 'lastName', 'formatDegrees', 'verified', 'npiNumber', 'nbcrnaId', 'cmeDuedate', 'modified')
    list_filter = ('verified','npiType')
    search_fields = ['npiNumber', 'lastName']
    filter_horizontal = ('specialties',)
    inlines = [
        ProfileCmetagInline,
    ]

    def get_queryset(self, request):
        qs = super(ProfileAdmin, self).get_queryset(request)
        return qs.prefetch_related('degrees')

class CustomerAdmin(admin.ModelAdmin):
    list_display = ('user', 'customerId', 'created')
    search_fields = ['customerId',]

class AffiliateAdmin(admin.ModelAdmin):
    list_display = ('user', 'affiliateId', 'paymentEmail', 'bonus', 'discountLabel', 'og_title', 'active','modified')
    list_filter = ('active',)
    ordering = ('paymentEmail',)

class StateLicenseAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'state', 'license_no', 'created')
    list_select_related = True

class SponsorAdmin(admin.ModelAdmin):
    list_display = ('id', 'abbrev', 'name', 'url', 'logo_url', 'modified')


class OfferTagInline(admin.TabularInline):
    model = OfferCmeTag

class BrowserCmeOfferAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'activityDateLocalTz', 'redeemed', 'url', 'suggestedDescr', 'valid', 'modified')
    #list_display = ('id', 'user', 'activityDate', 'redeemed', 'url', 'formatSuggestedTags', 'modified')
    list_select_related = ('user','eligible_site')
    list_filter = ('redeemed','eligible_site','user','valid')
    ordering = ('-modified',)
    inlines = [
        OfferTagInline,
    ]


class EntryTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created')

class DocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'content_type','document','md5sum', 'image_h','image_w', 'is_thumb', 'is_certificate', 'set_id', 'created')
    list_select_related = ('user',)

class EntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'entryType', 'activityDate', 'valid', 'description', 'created')
    list_filter = ('entryType', 'valid', 'user')
    list_select_related = ('user',)
    raw_id_fields = ('documents',)
    ordering = ('-created',)
    filter_horizontal = ('tags',)

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


class UserFeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'hasBias', 'hasUnfairContent', 'message_snippet', 'reviewed', 'created')
    list_filter = ('reviewed', 'hasBias', 'hasUnfairContent')
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


class DiscountAdmin(admin.ModelAdmin):
    list_display = ('id','discountType', 'activeForType', 'discountId','name','amount','numBillingCycles','created')
    ordering = ('discountType', '-created',)

class SignupDiscountAdmin(admin.ModelAdmin):
    list_display = ('id','email_domain','discount','expireDate')
    ordering = ('email_domain','expireDate')


class InvitationDiscountAdmin(admin.ModelAdmin):
    list_display = ('invitee_id', 'invitee', 'inviteeDiscount', 'inviter', 'inviterDiscount', 'inviterBillingCycle', 'creditEarned', 'created')
    list_select_related = True
    list_filter = ('creditEarned',)
    ordering = ('-created',)


class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('id', 'planId', 'name', 'price', 'monthlyPrice', 'discountPrice', 'discountMonthlyPrice', 'trialDays', 'billingCycleMonths', 'active', 'modified')
    ordering = ('-created',)


class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'subscriptionId', 'user', 'plan', 'status', 'display_status',
        'billingFirstDate', 'billingStartDate', 'billingEndDate', 'billingCycle', 'nextBillingAmount',
        'modified')
    list_select_related = ('user','plan')
    list_filter = ('status', 'display_status', 'remindRenewSent')
    ordering = ('-modified',)


class SubscriptionTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'transactionId', 'subscription', 'trans_type', 'amount', 'status', 'card_type', 'card_last4', 'receipt_sent', 'created', 'modified')
    list_select_related = ('subscription',)
    raw_id_fields = ('subscription',)
    list_filter = ('receipt_sent',)
    ordering = ('-modified',)


class CertificateAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'referenceId', 'name', 'startDate', 'endDate', 'credits', 'created')
    list_select_related = ('user',)
    search_fields = ['referenceId',]
    ordering = ('-created',)

class AuditReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'referenceId', 'name', 'startDate', 'endDate', 'saCredits', 'otherCredits', 'created')
    list_select_related = ('user',)
    search_fields = ['referenceId',]
    ordering = ('-created',)

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
    list_display = ('id', 'hostname', 'has_paywall', 'allow_page_download', 'accept_query_keys', 'created')
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
admin_site.register(AffiliatePayout, AffiliatePayoutAdmin)
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
admin_site.register(PinnedMessage, PinnedMessageAdmin)
admin_site.register(Profile, ProfileAdmin)
admin_site.register(PracticeSpecialty, PracticeSpecialtyAdmin)
admin_site.register(Sponsor, SponsorAdmin)
admin_site.register(StateLicense, StateLicenseAdmin)
admin_site.register(UserFeedback, UserFeedbackAdmin)
admin_site.register(SubscriptionPlan, SubscriptionPlanAdmin)
admin_site.register(UserSubscription, UserSubscriptionAdmin)
admin_site.register(SubscriptionTransaction, SubscriptionTransactionAdmin)
#
# plugin models
#
admin_site.register(AllowedHost, AllowedHostAdmin)
admin_site.register(HostPattern, HostPatternAdmin)
admin_site.register(AllowedUrl, AllowedUrlAdmin)
admin_site.register(RejectedUrl, RejectedUrlAdmin)
admin_site.register(RequestedUrl, RequestedUrlAdmin)
