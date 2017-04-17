from django.contrib import admin
from django.db.models import Count
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
    list_display = ('id', 'planId', 'name', 'price', 'trialDays', 'billingCycleMonths', 'active', 'modified')

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


admin.site.register(AuditReport, AuditReportAdmin)
admin.site.register(BrowserCmeOffer, BrowserCmeOfferAdmin)
admin.site.register(Certificate, CertificateAdmin)
admin.site.register(CmeTag, CmeTagAdmin)
admin.site.register(Country, CountryAdmin)
admin.site.register(Customer, CustomerAdmin)
admin.site.register(Degree, DegreeAdmin)
admin.site.register(Document, DocumentAdmin)
admin.site.register(EligibleSite, EligibleSiteAdmin)
admin.site.register(Entry, EntryAdmin)
admin.site.register(EntryType, EntryTypeAdmin)
admin.site.register(Profile, ProfileAdmin)
admin.site.register(PracticeSpecialty, PracticeSpecialtyAdmin)
admin.site.register(Sponsor, SponsorAdmin)
admin.site.register(UserFeedback, UserFeedbackAdmin)
admin.site.register(SubscriptionPlan, SubscriptionPlanAdmin)
admin.site.register(UserSubscription, UserSubscriptionAdmin)
#
# plugin models
#
admin.site.register(AllowedHost, AllowedHostAdmin)
admin.site.register(AllowedUrl, AllowedUrlAdmin)
admin.site.register(RequestedUrl, RequestedUrlAdmin)
