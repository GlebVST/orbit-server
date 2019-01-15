# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import pytz
from dal import autocomplete
from django import forms
from django.conf import settings
from django.contrib import admin
from django.db.models import Count
from mysite.admin import admin_site
from common.ac_filters import *
from common.dateutils import fmtLocalDatetime, makeAwareDatetime
from .models import *


class GoalTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'sort_order', 'description', 'created')

class BoardAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description', 'created')


class GoalRecForm(forms.ModelForm):
    class Meta:
        model = GoalRecommendation
        fields = ('__all__')
        widgets = {
            'pageTitle': forms.TextInput(attrs={'size': 80}),
            'url': forms.URLInput(attrs={'size': 100}),
        }

class GoalRecommendationInline(admin.StackedInline):
    model = GoalRecommendation
    form = GoalRecForm
    extra = 0

class LicenseGoalInline(admin.StackedInline):
    model = LicenseGoal
    extra = 0
    min_num = 1
    max_num = 1

class LicenseBaseGoalAdmin(admin.ModelAdmin):
    list_display = ('id', 'getTitle', 'interval', 'formatDegrees', 'formatSpecialties', 'getState', 'getLicenseType', 'getNumRecs', 'lastModified')
    list_filter = ('licensegoal__licenseType',)
    ordering = ('-modified',)
    inlines = (
        LicenseGoalInline,
        GoalRecommendationInline
    )
    filter_horizontal = (
        'degrees',
        'specialties',
    )
    exclude = ('modifiedBy', 'cmeTag')

    class Media:
        pass

    def get_queryset(self, request):
        qs = super(LicenseBaseGoalAdmin, self).get_queryset(request)
        return qs.select_related('goalType', 'licensegoal__licenseType', 'licensegoal__state').prefetch_related('degrees', 'specialties').annotate(num_recs=Count('recommendations'))

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

    def getNumRecs(self, obj):
        return obj.num_recs
    getNumRecs.short_description = 'Num Recs'

    def lastModified(self, obj):
        return fmtLocalDatetime(obj.modified)
    lastModified.short_description = 'Last Modified'
    lastModified.admin_order_field = 'modified'


class TrainingGoalForm(forms.ModelForm):
    class Meta:
        model = TrainingGoal
        fields = ('__all__')
        widgets = {
            'licenseGoal': autocomplete.ModelSelect2(
                url='licensegoal-autocomplete',
                attrs={
                    'data-placeholder': 'Select if dueDateType requires license expiration date',
                    'data-minimum-input-length': 2,
                }
            ),
            'state': autocomplete.ModelSelect2(
                url='statename-autocomplete',
                attrs={
                    'data-placeholder': 'State',
                    'data-minimum-input-length': 1,
                }
            ),
            'dueMonth': forms.NumberInput,
            'dueDay': forms.NumberInput
        }

class TrainingGoalInline(admin.StackedInline):
    model = TrainingGoal
    extra = 0
    min_num = 1
    max_num = 1
    form = TrainingGoalForm

class TrainingBaseGoalAdmin(admin.ModelAdmin):
    list_display = ('id', 'getTitle', 'interval', 'formatDegrees', 'formatSpecialties', 'getState', 'fmtDueDateType', 'getDueMMDD', 'getNumRecs', 'lastModified')
    list_filter = ('dueDateType',)
    ordering = ('-modified',)
    inlines = (
        TrainingGoalInline,
        GoalRecommendationInline
    )
    filter_horizontal = (
        'degrees',
        'specialties',
    )
    exclude = ('modifiedBy',)

    class Media:
        pass

    def get_queryset(self, request):
        qs = super(TrainingBaseGoalAdmin, self).get_queryset(request)
        return qs.select_related(
                'goalType', 'traingoal__state').prefetch_related('degrees', 'specialties').annotate(num_recs=Count('recommendations'))

    def get_changeform_initial_data(self, request):
        return {
                'goalType': GoalType.objects.get(name=GoalType.TRAINING),
                'dueDateType': BaseGoal.RECUR_LICENSE_DATE
            }

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit choice of goalType"""
        if db_field.name == 'goalType':
            kwargs['queryset'] = GoalType.objects.filter(name=GoalType.TRAINING)
        return super(TrainingBaseGoalAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        """Limit choice of dueDateType"""
        if db_field.name == 'dueDateType':
            kwargs['choices'] = TrainingGoal.DUEDATE_TYPE_CHOICES
        return super(TrainingBaseGoalAdmin, self).formfield_for_choice_field(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Set modifiedBy to request.user"""
        obj.modifiedBy = request.user
        super(TrainingBaseGoalAdmin, self).save_model(request, obj, form, change)

    def getTitle(self, obj):
        return obj.traingoal.title
    getTitle.short_description = 'Title'

    def getState(self, obj):
        return obj.traingoal.state
    getState.short_description = 'State'

    def getDueMMDD(self, obj):
        return obj.traingoal.dueMMDD
    getDueMMDD.short_description = 'Due MMDD'

    def fmtDueDateType(self, obj):
        return obj.formatDueDateType()
    fmtDueDateType.short_description = 'DueDateType'

    def getNumRecs(self, obj):
        return obj.num_recs
    getNumRecs.short_description = 'Num Recs'

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
            'licenseGoal': autocomplete.ModelSelect2(
                url='licensegoal-autocomplete',
                attrs={
                    'data-placeholder': 'Select if dueDateType requires license expiration date',
                    'data-minimum-input-length': 2,
                }
            ),
            'dueMonth': forms.NumberInput,
            'dueDay': forms.NumberInput
        }

    def clean(self):
        cleaned_data = super(CmeGoalForm, self).clean()
        dueMonth = cleaned_data.get('dueMonth')
        dueDay = cleaned_data.get('dueDay')
        if dueMonth and not dueDay:
            self.add_error('dueDay', 'dueDay and dueMonth must be specified together')
        if dueDay and not dueMonth:
            self.add_error('dueMonth', 'dueMonth and dueDay must be specified together')
        if dueMonth and dueDay:
            try:
                d = makeAwareDatetime(2020, dueMonth, dueDay)
            except ValueError:
                self.add_error('dueDay', 'Invalid date for the given dueDay and dueMonth.')

class CmeGoalInline(admin.StackedInline):
    model = CmeGoal
    extra = 0
    min_num = 1
    max_num = 1
    form = CmeGoalForm
    filter_horizontal = (
        'creditTypes',
    )

class CmeBaseGoalAdmin(admin.ModelAdmin):
    list_display = ('id', 'getEntityType', 'getEntityName', 'getTag', 'getCredits', 'interval', 'fmtDueDateType', 'getDueMMDD', 'formatDegrees', 'formatSpecialties', 'lastModified')
    list_filter = ('cmegoal__entityType', 'dueDateType', 'cmegoal__board',)
    ordering = ('-modified',)
    inlines = (CmeGoalInline,)
    filter_horizontal = (
        'degrees',
        'specialties',
        #'subspecialties' # TODO - needs additional validation to ensure selection agrees with specialties
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
        """Set modifiedBy to request.user, save object"""
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
        return obj.formatDueDateType()
    fmtDueDateType.short_description = 'DueDateType'

    def lastModified(self, obj):
        return fmtLocalDatetime(obj.modified)
    lastModified.short_description = 'Last Modified'
    lastModified.admin_order_field = 'modified'


class UserGoalAdmin(admin.ModelAdmin):
    list_display = ('id','user','goal','title','status','getDueDate','progress', 'license','creditsDue', 'lastModified')
    list_selected_related = True
    list_filter = ('status', 'goal__goalType', UserFilter)
    ordering = ('-modified',)

    class Media:
        pass

    def getDueDate(self, obj):
        return obj.dueDate.strftime('%Y-%m-%d')
    getDueDate.short_description = 'Due Date'

    def lastModified(self, obj):
        return fmtLocalDatetime(obj.modified)
    lastModified.short_description = 'Last Modified'
    lastModified.admin_order_field = 'modified'

# register models
admin_site.register(Board, BoardAdmin)
admin_site.register(GoalType, GoalTypeAdmin)
admin_site.register(LicenseBaseGoal, LicenseBaseGoalAdmin)
admin_site.register(TrainingBaseGoal, TrainingBaseGoalAdmin)
admin_site.register(CmeBaseGoal, CmeBaseGoalAdmin)
admin_site.register(UserGoal, UserGoalAdmin)
