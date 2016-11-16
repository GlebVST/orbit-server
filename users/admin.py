from django.contrib import admin
from .models import *

class DegreeAdmin(admin.ModelAdmin):
    list_display = ('abbrev', 'name', 'created')

class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'firstName', 'lastName', 'npiNumber', 'created')
    search_fields = ['npiNumber', 'lastName']

class CustomerAdmin(admin.ModelAdmin):
    list_display = ('user', 'contactEmail', 'customerId', 'balance', 'created')
    search_fields = ['contactEmail',]

class PointTransactionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'points', 'pricePaid', 'transactionId', 'created')

class PpoAdmin(admin.ModelAdmin):
    list_display = ('points', 'price', 'created')

admin.site.register(Customer, CustomerAdmin)
admin.site.register(Degree, DegreeAdmin)
admin.site.register(Profile, ProfileAdmin)
admin.site.register(PointTransaction, PointTransactionAdmin)
admin.site.register(PointPurchaseOption, PpoAdmin)
