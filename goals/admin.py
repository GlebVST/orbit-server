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
        'subspecialties',
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


class SRCmeGoalForm(forms.ModelForm):
    class Meta:
        model = SRCmeGoal
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
            'cmeTag': autocomplete.ModelSelect2(
                url='cmetag-autocomplete',
                attrs={
                    'data-placeholder': 'CmeTag',
                    'data-minimum-input-length': 1,
                }
            ),
            'dueMonth': forms.NumberInput,
            'dueDay': forms.NumberInput
        }

class SRCmeGoalInline(admin.StackedInline):
    model = SRCmeGoal
    extra = 0
    min_num = 1
    max_num = 1
    form = SRCmeGoalForm

class SRCmeBaseGoalAdmin(admin.ModelAdmin):
    list_display = ('id', 'getState', 'getTag', 'getCredits', 'interval', 'formatDegrees', 'formatSpecialties', 'fmtDueDateType', 'getDueMMDD')
    list_filter = ('srcmegoal__deaType', 'dueDateType', 'srcmegoal__state')
    ordering = ('-modified',)
    inlines = (
        SRCmeGoalInline,
        #GoalRecommendationInline
    )
    filter_horizontal = (
        'degrees',
        'specialties',
        'subspecialties', # TODO: add validation
    )
    exclude = ('modifiedBy',)

    class Media:
        pass

    def get_queryset(self, request):
        qs = super(SRCmeBaseGoalAdmin, self).get_queryset(request)
        return qs.select_related(
            'goalType', 'srcmegoal__state', 'srcmegoal__cmeTag') \
                .prefetch_related('degrees', 'specialties')

    def get_changeform_initial_data(self, request):
        return {
                'goalType': GoalType.objects.get(name=GoalType.SRCME),
                'dueDateType': BaseGoal.RECUR_LICENSE_DATE
            }

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit choice of goalType"""
        if db_field.name == 'goalType':
            kwargs['queryset'] = GoalType.objects.filter(name=GoalType.SRCME)
        return super(SRCmeBaseGoalAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        """Limit choice of dueDateType"""
        if db_field.name == 'dueDateType':
            kwargs['choices'] = SRCmeGoal.DUEDATE_TYPE_CHOICES
        return super(SRCmeBaseGoalAdmin, self).formfield_for_choice_field(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Set modifiedBy to request.user"""
        obj.modifiedBy = request.user
        super(SRCmeBaseGoalAdmin, self).save_model(request, obj, form, change)

    def getTag(self, obj):
        return obj.srcmegoal.cmeTag
    getTag.short_description = 'CmeTag'

    def getCredits(self, obj):
        if not obj.srcmegoal.has_credit:
            return 0
        return obj.srcmegoal.credits
    getCredits.short_description = 'Credits'

    def getState(self, obj):
        return obj.srcmegoal.state
    getState.short_description = 'State'

    def getDueMMDD(self, obj):
        return obj.srcmegoal.dueMMDD
    getDueMMDD.short_description = 'Due MMDD'

    def fmtDueDateType(self, obj):
        return obj.formatDueDateType()
    fmtDueDateType.short_description = 'DueDateType'

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
            'cmeTag': autocomplete.ModelSelect2(
                url='cmetag-autocomplete',
                attrs={
                    'data-placeholder': 'CmeTag',
                    'data-minimum-input-length': 1,
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
    list_display = ('id', 'getEntityType', 'getEntityName', 'getTag', 'getCredits', 'interval', 'fmtDueDateType', 'getDueMMDD', 'formatDegrees', 'formatSpecialties')
    list_filter = (
        'cmegoal__entityType',
        'cmegoal__deaType',
        'dueDateType',
        'cmegoal__board',
        'cmegoal__state',
        )
    ordering = ('-modified',)
    inlines = (CmeGoalInline,)
    filter_horizontal = (
        'degrees',
        'specialties',
        'subspecialties' # TODO - needs additional validation to ensure selection agrees with specialties
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
        return obj.cmegoal.getTag()
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
    list_display = ('id','user','goal','title','status','getDueDate','progress', 'is_composite_goal','creditsDue', 'creditsEarned')
    list_selected_related = True
    list_filter = ('is_composite_goal', 'status', 'goal__goalType', UserFilter)
    ordering = ('-modified',)
    raw_id_fields = ('documents','constituentGoals',)

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
admin_site.register(SRCmeBaseGoal, SRCmeBaseGoalAdmin)
admin_site.register(CmeBaseGoal, CmeBaseGoalAdmin)
admin_site.register(UserGoal, UserGoalAdmin)
