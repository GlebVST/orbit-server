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
    list_display = ('user', 'firstName', 'lastName', 'contactEmail', 'verified', 'npiNumber', 'country', 'inviter', 'modified')
    list_filter = ('country','verified')
    list_select_related = ('country','inviter')
    search_fields = ['npiNumber', 'lastName']

class CustomerAdmin(admin.ModelAdmin):
    list_display = ('user', 'customerId', 'balance', 'modified')
    search_fields = ['customerId',]

class BrowserCmeOfferAdmin(admin.ModelAdmin):
    list_display = ('user', 'activityDate', 'redeemed', 'expireDate', 'url')
    list_filter = ('redeemed',)

class EntryTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created')

class DocumentAdmin(admin.ModelAdmin):
    list_display = ('user', 'uploadId', 'name', 'content_type','document','image_h','image_w','md5sum','created')
    list_select_related = ('user',)

class EntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'entryType', 'activityDate', 'valid', 'description', 'created')
    list_filter = ('entryType', 'valid')

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

admin.site.register(BrowserCmeOffer, BrowserCmeOfferAdmin)
admin.site.register(CmeTag, CmeTagAdmin)
admin.site.register(Country, CountryAdmin)
admin.site.register(Customer, CustomerAdmin)
admin.site.register(Degree, DegreeAdmin)
admin.site.register(Document, DocumentAdmin)
admin.site.register(Entry, EntryAdmin)
admin.site.register(EntryType, EntryTypeAdmin)
admin.site.register(Profile, ProfileAdmin)
admin.site.register(PracticeSpecialty, PracticeSpecialtyAdmin)
admin.site.register(UserFeedback, UserFeedbackAdmin)
admin.site.register(SubscriptionPlan, SubscriptionPlanAdmin)
admin.site.register(UserSubscription, UserSubscriptionAdmin)
