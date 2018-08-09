# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import pytz
from dal import autocomplete
from django import forms
from django.conf import settings
from django.contrib import admin
from mysite.admin import admin_site
from common.ac_filters import *
from common.dateutils import fmtLocalDatetime
from .models import *


class GoalTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description', 'created')

class BoardAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description', 'created')

class LicenseGoalInline(admin.StackedInline):
    model = LicenseGoal
    extra = 0
    min_num = 1
    max_num = 1

class LicenseBaseGoalAdmin(admin.ModelAdmin):
    list_display = ('id', 'getTitle', 'interval', 'formatDegrees', 'formatSpecialties', 'getState', 'getLicenseType', 'lastModified')
    list_filter = ('licensegoal__licenseType',)
    ordering = ('-modified',)
    inlines = (LicenseGoalInline,)
    filter_horizontal = (
        'degrees',
        'specialties',
    )
    exclude = ('modifiedBy',)

    class Media:
        pass

    def get_queryset(self, request):
        qs = super(LicenseBaseGoalAdmin, self).get_queryset(request)
        return qs.select_related('goalType', 'licensegoal__licenseType', 'licensegoal__state').prefetch_related('degrees', 'specialties')

    def get_changeform_initial_data(self, request):
        return {
                'goalType': GoalType.objects.get(name=GoalType.LICENSE),
                'dueDateType': BaseGoal.RECUR_LICENSE_DATE
            }

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit choice of goalType"""
        if db_field.name == 'goalType':
            kwargs['queryset'] = GoalType.objects.filter(name=GoalType.LICENSE)
        return super(LicenseBaseGoalAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        """Limit choice of dueDateType"""
        if db_field.name == 'dueDateType':
            kwargs['choices'] = LicenseGoal.DUEDATE_TYPE_CHOICES
        return super(LicenseBaseGoalAdmin, self).formfield_for_choice_field(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Set modifiedBy to request.user"""
        obj.modifiedBy = request.user
        super(LicenseBaseGoalAdmin, self).save_model(request, obj, form, change)

    def getTitle(self, obj):
        return obj.licensegoal.title
    getTitle.short_description = 'Title'

    def getState(self, obj):
        return obj.licensegoal.state
    getState.short_description = 'State'

    def getLicenseType(self, obj):
        return obj.licensegoal.licenseType
    getLicenseType.short_description = 'LicenseType'

    def lastModified(self, obj):
        return fmtLocalDatetime(obj.modified)
    lastModified.short_description = 'Last Modified'
    lastModified.admin_order_field = 'modified'


class CmeGoalForm(forms.ModelForm):
    class Meta:
        model = CmeGoal
        fields = ('__all__')
        widgets = {
            'hospital': autocomplete.ModelSelect2(
                url='hospital-autocomplete',
                attrs={
                    'data-placeholder': 'Select if entityType is Hospital',
                    'data-minimum-input-length': 2,
                }
            ),
            'state': autocomplete.ModelSelect2(
                url='statename-autocomplete',
                attrs={
                    'data-placeholder': 'Select if entityType is State',
                    'data-minimum-input-length': 1,
                }
            ),
        }

class CmeGoalInline(admin.StackedInline):
    model = CmeGoal
    extra = 0
    min_num = 1
    max_num = 1
    form = CmeGoalForm

class CmeBaseGoalAdmin(admin.ModelAdmin):
    list_display = ('id', 'getEntityType', 'getEntityName', 'getTag', 'getCredits', 'interval', 'fmtDueDateType', 'getDueMMDD', 'formatDegrees', 'formatSpecialties', 'lastModified')
    list_filter = ('cmegoal__entityType', 'dueDateType', 'cmegoal__board',)
    ordering = ('-modified',)
    inlines = (CmeGoalInline,)
    filter_horizontal = (
        'degrees',
        'specialties',
    )
    exclude = ('modifiedBy',)

    class Media:
        pass

    def get_queryset(self, request):
        qs = super(CmeBaseGoalAdmin, self).get_queryset(request)
        return qs.select_related('goalType', 'cmegoal__board', 'cmegoal__state', 'cmegoal__hospital').prefetch_related('degrees', 'specialties')

    def get_changeform_initial_data(self, request):
        return {
                'goalType': GoalType.objects.get(name=GoalType.CME),
            }

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit choice of goalType"""
        if db_field.name == 'goalType':
            kwargs['queryset'] = GoalType.objects.filter(name=GoalType.CME)
        return super(CmeBaseGoalAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Set modifiedBy to request.user"""
        obj.modifiedBy = request.user
        super(CmeBaseGoalAdmin, self).save_model(request, obj, form, change)

    def getEntityType(self, obj):
        etype = obj.cmegoal.entityType
        return CmeGoal.ENTITY_TYPE_CHOICES[etype][1] # label
    getEntityType.short_description = 'Entity Type'

    def getEntityName(self, obj):
        return obj.cmegoal.entityName
    getEntityName.short_description = 'Entity'

    def getTag(self, obj):
        return obj.cmegoal.cmeTag if obj.cmegoal.cmeTag else u'(Any)'
    getTag.short_description = 'CME Tag'

    def getCredits(self, obj):
        return obj.cmegoal.credits
    getCredits.short_description = 'Credits'

    def getDueMMDD(self, obj):
        return obj.cmegoal.dueMMDD
    getDueMMDD.short_description = 'Due MMDD'


    def fmtDueDateType(self, obj):
        if obj.dueDateType == BaseGoal.ONE_OFF:
            return u'One-off'
        if obj.dueDateType == BaseGoal.RECUR_MMDD:
            return u'Fixed MM/DD'
        if obj.dueDateType == BaseGoal.RECUR_ANY:
            return u'Any time'
        if obj.dueDateType == BaseGoal.RECUR_BIRTH_DATE:
            return u'Birthdate'
        return u'License expireDate'
    fmtDueDateType.short_description = 'DueDate Type'

    def lastModified(self, obj):
        return fmtLocalDatetime(obj.modified)
    lastModified.short_description = 'Last Modified'
    lastModified.admin_order_field = 'modified'


# register models
admin_site.register(Board, BoardAdmin)
admin_site.register(GoalType, GoalTypeAdmin)
admin_site.register(LicenseBaseGoal, LicenseBaseGoalAdmin)
admin_site.register(CmeBaseGoal, CmeBaseGoalAdmin)
