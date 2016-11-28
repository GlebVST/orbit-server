from django.contrib import admin
from .models import *

class DegreeAdmin(admin.ModelAdmin):
    list_display = ('abbrev', 'name', 'created')

class PracticeSpecialtyAdmin(admin.ModelAdmin):
    list_display = ('name', 'created')

class CmeTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'created')


class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'firstName', 'lastName', 'npiNumber', 'created')
    search_fields = ['npiNumber', 'lastName']

class CustomerAdmin(admin.ModelAdmin):
    list_display = ('user', 'contactEmail', 'customerId', 'balance', 'created')
    search_fields = ['contactEmail',]

class BrowserCmeOfferAdmin(admin.ModelAdmin):
    list_display = ('user', 'activityDate', 'redeemed', 'expireDate', 'url')
    list_filter = ('redeemed',)

class EntryTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created')

class EntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'entryType', 'activityDate', 'valid', 'description')
    list_filter = ('entryType', 'valid')

class PointTransactionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'points', 'pricePaid', 'transactionId', 'created')

class PpoAdmin(admin.ModelAdmin):
    list_display = ('points', 'price', 'created')

class ProAdmin(admin.ModelAdmin):
    list_display = ('points', 'rewardType', 'description', 'created')

class PpoAdmin(admin.ModelAdmin):
    list_display = ('points', 'price', 'created')

class UserFeedbackAdmin(admin.ModelAdmin):
    list_display = ('user', 'hasBias', 'hasUnfairContent', 'created')
    list_filter = ('hasBias', 'hasUnfairContent')


admin.site.register(BrowserCmeOffer, BrowserCmeOfferAdmin)
admin.site.register(CmeTag, CmeTagAdmin)
admin.site.register(Customer, CustomerAdmin)
admin.site.register(Degree, DegreeAdmin)
admin.site.register(Entry, EntryAdmin)
admin.site.register(EntryType, EntryTypeAdmin)
admin.site.register(Profile, ProfileAdmin)
admin.site.register(PointTransaction, PointTransactionAdmin)
admin.site.register(PointPurchaseOption, PpoAdmin)
admin.site.register(PointRewardOption, ProAdmin)
admin.site.register(PracticeSpecialty, PracticeSpecialtyAdmin)
admin.site.register(UserFeedback, UserFeedbackAdmin)
