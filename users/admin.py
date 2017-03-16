from django.contrib import admin
from .models import *

class DegreeAdmin(admin.ModelAdmin):
    list_display = ('id', 'abbrev', 'name', 'created')

class PracticeSpecialtyAdmin(admin.ModelAdmin):
    list_display = ('name', 'created')

class CmeTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'priority', 'description', 'created')

class CountryAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'created')

class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'firstName', 'lastName', 'contactEmail', 'verified', 'npiNumber', 'country', 'inviter', 'cmeDuedate', 'modified')
    list_filter = ('country','verified')
    list_select_related = ('country','inviter')
    search_fields = ['npiNumber', 'lastName']

class CustomerAdmin(admin.ModelAdmin):
    list_display = ('user', 'customerId', 'balance', 'modified')
    search_fields = ['customerId',]

class SponsorAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'logo_url', 'modified')

class BrowserCmeOfferAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'activityDate', 'redeemed', 'expireDate', 'url')
    list_filter = ('redeemed',)

class EntryTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created')

class DocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'content_type','document','md5sum', 'image_h','image_w', 'is_thumb', 'is_certificate', 'set_id', 'created')
    list_select_related = ('user',)

class EntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'entryType', 'activityDate', 'valid', 'description', 'created')
    list_filter = ('entryType', 'valid')
    raw_id_fields = ('documents',)

class EligibleSiteAdmin(admin.ModelAdmin):
    list_display = ('id', 'domain_name', 'domain_title', 'example_title', 'example_url', 'is_valid_expurl', 'needs_ad_block', 'modified')
    list_filter = ('is_valid_expurl', 'needs_ad_block')


class UserFeedbackAdmin(admin.ModelAdmin):
    list_display = ('user', 'hasBias', 'hasUnfairContent', 'created')
    list_filter = ('hasBias', 'hasUnfairContent')

class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('planId', 'name', 'price', 'trialDays', 'billingCycleMonths', 'active', 'modified')

class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('subscriptionId', 'user', 'plan', 'status', 'display_status', 
        'billingFirstDate', 'billingStartDate', 'billingEndDate', 'billingCycle',
        'created', 'modified')
    list_select_related = ('user','plan')
    list_filter = ('status', 'display_status')

class CertificateAdmin(admin.ModelAdmin):
    list_display = ('user', 'referenceId', 'name', 'startDate', 'endDate', 'credits', 'created')
    list_select_related = ('user',)
    search_fields = ['referenceId',]


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
