from django import forms
from django.contrib import admin
from django.db.models import Count
from pagedown.widgets import AdminPagedownWidget
from .models import *

class DegreeAdmin(admin.ModelAdmin):
    list_display = ('id', 'abbrev', 'name', 'created')

class PracticeSpecialtyAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'formatTags', 'created')

    def get_queryset(self, request):
        qs = super(PracticeSpecialtyAdmin, self).get_queryset(request)
        return qs.prefetch_related('cmeTags')

class CmeTagAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'priority', 'description', 'created')

class CountryAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'created')

class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'firstName', 'lastName', 'formatDegrees', 'contactEmail', 'verified', 'npiNumber', 'cmeDuedate', 'modified')
    list_filter = ('verified',)
    search_fields = ['npiNumber', 'lastName']

    def get_queryset(self, request):
        qs = super(ProfileAdmin, self).get_queryset(request)
        return qs.prefetch_related('degrees')

class CustomerAdmin(admin.ModelAdmin):
    list_display = ('user', 'customerId', 'created')
    search_fields = ['customerId',]

class SponsorAdmin(admin.ModelAdmin):
    list_display = ('id', 'abbrev', 'name', 'url', 'logo_url', 'modified')

class BrowserCmeOfferAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'activityDate', 'redeemed', 'expireDate', 'url')
    list_select_related = ('user',)
    list_filter = ('redeemed',)
    ordering = ('-activityDate',)

class EntryTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created')

class DocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'content_type','document','md5sum', 'image_h','image_w', 'is_thumb', 'is_certificate', 'set_id', 'created')
    list_select_related = ('user',)

class EntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'entryType', 'activityDate', 'valid', 'description', 'created')
    list_filter = ('entryType', 'valid')
    list_select_related = ('user',)
    raw_id_fields = ('documents',)
    ordering = ('-created',)

class EligibleSiteAdmin(admin.ModelAdmin):
    list_display = ('id', 'domain_name', 'domain_title', 'example_title', 'example_url', 'is_valid_expurl', 'needs_ad_block', 'modified')
    list_filter = ('is_valid_expurl', 'needs_ad_block')
    ordering = ('domain_name',)

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



class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('id', 'planId', 'name', 'price', 'monthlyPrice', 'discountPrice', 'discountMonthlyPrice', 'trialDays', 'billingCycleMonths', 'active', 'modified')
    
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'subscriptionId', 'user', 'plan', 'status', 'display_status',
        'billingFirstDate', 'billingStartDate', 'billingEndDate', 'billingCycle',
        'created', 'modified')
    list_select_related = ('user','plan')
    list_filter = ('status', 'display_status')
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

#
# plugin models
#
class AllowedHostAdmin(admin.ModelAdmin):
    list_display = ('id', 'hostname', 'created', 'modified')
    ordering = ('-modified',)

class AllowedUrlAdmin(admin.ModelAdmin):
    list_display = ('id', 'host', 'url', 'eligible_site', 'valid', 'created')
    list_select_related = ('host', 'eligible_site')
    list_filter = ('host',)
    ordering = ('-modified',)

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
admin_site.register(AuditReport, AuditReportAdmin)
admin_site.register(BrowserCmeOffer, BrowserCmeOfferAdmin)
admin_site.register(Certificate, CertificateAdmin)
admin_site.register(CmeTag, CmeTagAdmin)
admin_site.register(Country, CountryAdmin)
admin_site.register(Customer, CustomerAdmin)
admin_site.register(Degree, DegreeAdmin)
admin_site.register(Document, DocumentAdmin)
admin_site.register(EligibleSite, EligibleSiteAdmin)
admin_site.register(Entry, EntryAdmin)
admin_site.register(EntryType, EntryTypeAdmin)
admin_site.register(PinnedMessage, PinnedMessageAdmin)
admin_site.register(Profile, ProfileAdmin)
admin_site.register(PracticeSpecialty, PracticeSpecialtyAdmin)
admin_site.register(Sponsor, SponsorAdmin)
admin_site.register(UserFeedback, UserFeedbackAdmin)
admin_site.register(SubscriptionPlan, SubscriptionPlanAdmin)
admin_site.register(UserSubscription, UserSubscriptionAdmin)
#
# plugin models
#
admin_site.register(AllowedHost, AllowedHostAdmin)
admin_site.register(AllowedUrl, AllowedUrlAdmin)
admin_site.register(RequestedUrl, RequestedUrlAdmin)
