# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django import forms
from django.contrib import admin,messages
from django.db.models import Count, Q, Subquery
from django.utils.safestring import mark_safe
from django.utils import timezone
from dal import autocomplete
from mysite.admin import admin_site
from common.ac_filters import UserFilter, CmeTagFilter, TagFilter, StateFilter, EligibleSiteFilter 
from common.dateutils import fmtLocalDatetime
from .models import *
from django.utils.html import format_html
from django.urls import reverse, NoReverseMatch
from django.http import HttpResponseRedirect
from django.conf.urls import url
from users.csv_tools import ProviderCsvImport
from io import StringIO

class AuthImpersonationForm(forms.ModelForm):
    class Meta:
        model = AuthImpersonation
        fields = ('__all__')
        widgets = {
            'impersonatee': autocomplete.ModelSelect2(
                url='useremail-autocomplete',
                attrs={
                    'data-minimum-input-length': 2
                }
            )
        }

class AuthImpersonationAdmin(admin.ModelAdmin):
    list_display = ('id', 'impersonator', 'impersonatee', 'valid', 'expireDate')
    form = AuthImpersonationForm

class DegreeAdmin(admin.ModelAdmin):
    list_display = ('id', 'abbrev', 'name', 'sort_order', 'created')


class PracticeSpecialtyAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'gsearchEngineid', 'formatTags', 'formatSubSpecialties')
    filter_horizontal = ('cmeTags',)

    def get_queryset(self, request):
        qs = super(PracticeSpecialtyAdmin, self).get_queryset(request)
        return qs.prefetch_related('cmeTags', 'subspecialties')

    def gsearchEngineid(self, obj):
        return obj.gsearchengid
    gsearchEngineid.short_description = 'GSearchEngineID'

class SubSpecialtyAdmin(admin.ModelAdmin):
    list_display = ('id', 'specialty', 'name', 'formatTags')
    filter_horizontal = ('cmeTags',)
    list_select_related = True
    list_filter = ('specialty',)

    def get_queryset(self, request):
        qs = super(SubSpecialtyAdmin, self).get_queryset(request)
        return qs.prefetch_related('cmeTags')


class OrgForm(forms.ModelForm):
    class Meta:
        model = Organization
        exclude = (
            'joinCode',
            'credits',
            'providerStat',
            'created',
            'modified'
        )

    def save(self, commit=True):
        """Auto assign joinCode based on code"""
        m = super(OrgForm, self).save(commit=False)
        m.joinCode = m.code.replace(' ', '').lower()
        if not m.creditStartDate:
            m.creditStartDate = timezone.now()
        m.save()
        return m

class OrgGroupInline(admin.TabularInline):
    model = OrgGroup

class OrgPlansetInline(admin.TabularInline):
    model = OrgPlanset

class OrgAdmin(admin.ModelAdmin):
    list_display = ('id', 'joinCode', 'code', 'name', 'email_domain', 'activateGoals', 'credits', 'creditStartDate', 'enterprisePlan', 'advancedPlan')
    list_filter = ('activateGoals',)
    form = OrgForm
    ordering = ('joinCode',)
    inlines = [
        OrgGroupInline,
        OrgPlansetInline,
    ]

    def enterprisePlan(self, obj):
        p = obj.getEnterprisePlan()
        if p:
            return p.name
        return ''

    def advancedPlan(self, obj):
        p = obj.getAdvancedPlan()
        if p:
            return p.name
        return ''

class OrgAggAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'day', 'users_invited', 'users_active', 'users_inactive', 'licenses_expired', 'licenses_expiring',
            'cme_gap_expired', 'cme_gap_expiring')
    list_filter = ('organization',)
    ordering = ('-day',)
    date_hierarchy = 'day'


class OrgFileForm(forms.ModelForm):
    class Meta:
        model = OrgFile
        fields = ('user','organization','document','csvfile','name','file_type','content_type', 'processed')

    def clean(self):
        """Check the user is an admin for the given org"""
        cleaned_data = super(OrgFileForm, self).clean()
        user = cleaned_data.get('user')
        org = cleaned_data.get('organization')
        qs = OrgMember.objects.filter(organization=org, is_admin=True, user=user)
        if not qs.exists():
            self.add_error('user', 'This user is not an administrator of the selected Organization: {0.code}'.format(org))


class OrgFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'user', 'file_type', 'name', 'document', 'validated', 'created', 'orgfile_actions')
    list_filter = ('file_type', 'organization')
    readonly_fields = ('orgfile_actions',)
    list_select_related = True
    ordering = ('-created',)
    form = OrgFileForm

    class Media:
        pass

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit choice of user"""
        if db_field.name == 'user':
            admin_users = OrgMember.objects.filter(is_admin=True, removeDate__isnull=True)
            kwargs['queryset'] = User.objects.filter(pk__in=Subquery(admin_users.values('user'))).order_by('email')
        return super(OrgFileAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def get_urls(self):
        urls = super(OrgFileAdmin, self).get_urls()
        custom_urls = [
            url(
                r'^(?P<id>.+)/process/$',
                self.admin_site.admin_view(self.orgfile_process),
                name='orgfile-process',
            ),
        ]
        return custom_urls + urls

    def orgfile_actions(self, obj):
        """TODO: the action should be different depending on the file_type"""
        return format_html(
            '<a class="button" href="{}">Import New Users</a>',
            reverse('admin:orgfile-process', args=[obj.pk]),
        )
    orgfile_actions.short_description = 'File Actions'
    orgfile_actions.allow_tags = True

    def orgfile_process(self,  request, id, *args, **kwargs):
        orgfile = self.get_object(request, id)
        org = orgfile.organization
        src_file = orgfile.csvfile if orgfile.csvfile else orgfile.document
        output = StringIO()
        csv = ProviderCsvImport(stdout=output)
        success = csv.processOrgFile(org_id=org.id, src_file=src_file, dry_run=True)
        if success:
            self.message_user(request, 'Success')
        else:
            self.message_user(request, output.getvalue(), messages.WARNING)
        url = reverse(
            'admin:users_orgfile_change',
            args=[orgfile.pk],
            current_app=self.admin_site.name,
        )
        return HttpResponseRedirect(url)

class OrgMemberAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'group', 'user', 'fullname', 'is_admin', 'pending', 'numArticlesRead30', 'removeDate')
    list_select_related = True
    list_filter = ('is_admin', 'pending', 'setPasswordEmailSent', 'organization', UserFilter)
    raw_id_fields = ('orgfiles',)
    ordering = ('-created','fullname')

    class Media:
        pass

class OrgEnrolleeAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'group', 'npiNumber', 'lastName','firstName','user','planName','enrollDate')
    list_select_related = True
    ordering = ('enrollDate','lastName')

    class Media:
        pass

class OrgReportForm(forms.ModelForm):
    class Meta:
        model = OrgReport
        fields = ('name','description','resource','active')

    def clean(self):
        """Check that resource name can be properly reversed into a url"""
        cleaned_data = super(OrgReportForm, self).clean()
        if cleaned_data['resource']:
            try:
                url = reverse(cleaned_data['resource'])
            except NoReverseMatch:
                self.add_error('resource', 'Invalid endpoint name. Could not reverse to actual endpoint url. Check urls.py')

class OrgReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description', 'resource', 'last_generated', 'active', 'created')
    ordering = ('id',)
    form = OrgReportForm

class CmeTagForm(forms.ModelForm):

    class Meta:
        model = CmeTag
        exclude = (
            'created',
            'modified'
        )

    def clean(self):
        """Validation checks:
        If abbrev given, check that abbrev (case-i) is unique
        """
        cleaned_data = super(CmeTagForm, self).clean()
        lc_abbrev = cleaned_data.get('abbrev').lower()
        if lc_abbrev:
            cleaned_data['abbrev'] = lc_abbrev
            qs = CmeTag.objects.filter(abbrev__iexact=lc_abbrev)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk) # exclude self
            if qs.exists():
                self.add_error('abbrev', 'Abbrevation for ABA EventId must be case-insensitive unique across all tags.')
        return cleaned_data

class CmeTagAdmin(admin.ModelAdmin):
    list_display = ('id', 'category', 'abbrev', 'name', 'description', 'srcme_only', 'priority', 'exemptFrom1Tag', 'instructions')
    list_filter = ('exemptFrom1Tag', 'srcme_only','category')
    list_select_related = ('category',)
    form = CmeTagForm

class CountryAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'created')

class StateAdmin(admin.ModelAdmin):
    list_display = ('id', 'country', 'name', 'abbrev', 'rnCertValid', 'formatTags', 'formatDEATags', 'formatDOTags')
    list_filter = ('rnCertValid',)
    filter_horizontal = ('cmeTags', 'deaTags', 'doTags')

    def get_queryset(self, request):
        qs = super(StateAdmin, self).get_queryset(request)
        return qs.prefetch_related('cmeTags', 'deaTags')


class ResidencyProgramAdmin(admin.ModelAdmin):
    list_display = ('id','name',)

class HospitalAdmin(admin.ModelAdmin):
    list_display = ('id','state','display_name','city')
    list_filter = (StateFilter,)
    list_select_related = ('state',)

    class Media:
        pass


class ProfileCmetagInline(admin.TabularInline):
    model = ProfileCmetag

class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'firstName',
        'lastName',
        'formatDegrees',
        'organization',
        'verified',
        'professionalId',
        'planId',
        'formatSpecialties',
    )
    list_select_related = ('organization',)
    list_filter = ('verified', 'allowArticleSearch', UserFilter,'degrees', 'organization', 'specialties')
    search_fields = ['user__email', 'npiNumber', 'lastName', 'ABANumber', 'ABIMNumber']
    filter_horizontal = (
        'specialties',
        'subspecialties',
        'hospitals',
        'states'
    )
    inlines = [
        ProfileCmetagInline,
    ]
    actions = ('toggleAllowArticleSearch',)
    class Media:
        pass


    def get_actions(self, request):
        """Remove default bulk-delete operation since it should be in sync w. auth0"""
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def toggleAllowArticleSearch(self, request, queryset):
        num_users = len(queryset)
        if num_users == 0:
            errmsg = 'Select user profile (use the User Filter dropdown menu if needed), and then select this action to toggle permission.'
            self.message_user(request, errmsg, level=messages.ERROR)
            return
        data = []
        for profile in queryset:
            profile.allowArticleSearch = not profile.allowArticleSearch
            profile.save(update_fields=('allowArticleSearch',))
            if profile.allowArticleSearch:
                status = "ON"
            else:
                status = "OFF"
            data.append("{0}: {1}".format(profile, status))
        msg = "Toggled Related Article Rail permission for num_users: {0}<br />".format(num_users)
        msg += "<br />".join(data)
        self.message_user(request, mark_safe(msg), level=messages.SUCCESS)
    toggleAllowArticleSearch.short_description = 'Select user profile to toggle Related Article rail permission'

    def get_queryset(self, request):
        qs = super(ProfileAdmin, self).get_queryset(request)
        return qs.prefetch_related('degrees', 'specialties')

    def professionalId(self, obj):
        if obj.ABIMNumber:
            return "abim:{0.ABIMNumber}".format(obj)
        if obj.ABANumber:
            return "aba:{0.ABANumber}".format(obj)
        if obj.npiNumber:
            return "npi:{0.npiNumber}".format(obj)
        return ''

class CustomerAdmin(admin.ModelAdmin):
    list_display = ('user', 'customerId', 'balance', 'modified')
    search_fields = ['customerId',]

class AffiliateForm(forms.ModelForm):

    class Meta:
        model = Affiliate
        exclude = (
            'created',
            'modified'
        )

    def clean(self):
        """Validation checks
        """
        cleaned_data = super(AffiliateForm, self).clean()
        bonus = cleaned_data.get('bonus')
        payout = cleaned_data.get('payout')
        if bonus and payout or (not bonus and not payout):
            self.add_error('bonus', 'Bonus and Fixed Payout are mutually exclusive. Exactly one must be specified and the other left blank.')
        if bonus and bonus < 0:
            self.add_error('bonus', 'Bonus must be a value between 0 and 1.')
        if payout and payout < 0:
            self.add_error('payout', 'Fixed payout must be a positive number.')

class AffiliateAdmin(admin.ModelAdmin):
    list_display = ('user', 'displayLabel', 'paymentEmail', 'bonus', 'payout', 'modified')
    form = AffiliateForm
    ordering = ('displayLabel',)

class AffiliateDetailAdmin(admin.ModelAdmin):
    list_display = ('affiliateId', 'affiliate', 'redirect_page', 'jobDescription', 'photoUrl', 'modified')
    ordering = ('affiliate','affiliateId')


class LicenseTypeAdmin(admin.ModelAdmin):
    list_display = ('id','name','created')

class StateLicenseAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'state', 'licenseType', 'licenseNumber', 'expireDate', 'created')
    list_select_related = True
    list_filter = ('licenseType', 'is_active', StateFilter, UserFilter)
    ordering = ('-expireDate','user')

    class Media:
        pass

class SponsorAdmin(admin.ModelAdmin):
    list_display = ('id', 'abbrev', 'name', 'url', 'logo_url', 'modified')


class CreditTypeAdmin(admin.ModelAdmin):
    list_display = ('abbrev', 'name', 'auditname', 'sort_order', 'formatDegrees')
    filter_horizontal = ('degrees',)

    def get_queryset(self, request):
        qs = super(CreditTypeAdmin, self).get_queryset(request)
        return qs.prefetch_related('degrees')

class EntryTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created')

class DocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'content_type','document','md5sum', 'image_h','image_w', 'is_thumb', 'is_certificate', 'set_id', 'created')
    list_select_related = True

class EntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'description','formatTags','created','submitABADate','submitABIMDate')
    list_filter = ('entryType', 'valid', UserFilter, 'tags')
    list_select_related = True
    raw_id_fields = ('documents',)
    ordering = ('-created',)
    filter_horizontal = ('tags',)
    date_hierarchy = 'submitABADate'

    class Media:
        pass

    def get_queryset(self, request):
        qs = super(EntryAdmin, self).get_queryset(request)
        return qs.prefetch_related('tags')


class ArticleTypeInline(admin.TabularInline):
    model = ArticleType

class EligibleSiteAdmin(admin.ModelAdmin):
    list_display = ('id', 'domain_name', 'domain_title', 'page_title_suffix', 'page_title_prefix', 'strip_title_after', 'formatArticleTypes')
    list_filter = ('needs_ad_block', 'all_specialties', 'is_unlisted', 'verify_journal')
    ordering = ('domain_name',)
    filter_horizontal = ('specialties',)
    inlines = [
        ArticleTypeInline,
    ]

    def formatArticleTypes(self, obj):
        qs = obj.articletypes.all()
        ats = []
        for m in qs:
            if m.is_allowed:
                ats.append("<b>{0.name}</b>".format(m))
            else:
                ats.append(m.name)
        return ','.join(ats)
    formatArticleTypes.allow_tags = True

class UserFeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'hasBias', 'hasUnfairContent', 'message_snippet', 'reviewed', 'created')
    list_filter = ('reviewed', 'hasBias', 'hasUnfairContent', UserFilter)
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

    class Media:
        pass


class DiscountAdmin(admin.ModelAdmin):
    list_display = ('id','discountType', 'activeForType', 'discountId','name','amount','numBillingCycles','created')
    ordering = ('discountType', '-created',)

class SignupDiscountAdmin(admin.ModelAdmin):
    list_display = ('id','organization','email_domain','discount','expireDate')
    ordering = ('organization','expireDate')

class SignupEmailPromoForm(forms.ModelForm):

    class Meta:
        model = SignupEmailPromo
        fields = ('__all__')

    def clean_email(self):
        self.cleaned_data['email'] = self.cleaned_data['email'].lower()
        return self.cleaned_data['email']

    def clean(self):
        cleaned_data = super(SignupEmailPromoForm, self).clean()
        v = cleaned_data.get('email', '')
        if v and SignupEmailPromo.objects.filter(email=v).exists():
            self.add_error('email', 'Case-insensitive email address already exists for this email.')
        fyp = cleaned_data['first_year_price']
        fyd = cleaned_data['first_year_discount']
        if fyp and fyd:
            self.add_error('first_year_discount', 'Specify either first_year_price or first_year_discount.')
        if not fyp and not fyd:
            self.add_error('first_year_discount', 'Specify either first_year_price or first_year_discount.')

class SignupEmailPromoAdmin(admin.ModelAdmin):
    list_display = ('id','email','first_year_price','first_year_discount', 'display_label', 'created')
    ordering = ('-created',)
    search_fields = ['email',]
    form = SignupEmailPromoForm

class InvitationDiscountAdmin(admin.ModelAdmin):
    list_display = ('invitee', 'inviteeDiscount', 'inviter', 'inviterDiscount', 'inviterBillingCycle', 'creditEarned', 'created')
    list_select_related = True
    list_filter = ('creditEarned',)
    ordering = ('-created',)


class SubscriptionPlanTypeAdmin(admin.ModelAdmin):
    list_display = ('id','name', 'needs_payment_method')

class SubscriptionPlanKeyAdmin(admin.ModelAdmin):
    list_display = ('id','name','degree','specialty','description','use_free_plan', 'video_url', 'created')
    list_select_related = True
    list_filter = ('use_free_plan', 'degree','specialty')
    ordering = ('-created',)

class PlanForm(forms.ModelForm):

    class Meta:
        model = SubscriptionPlan
        exclude = (
            'planId',
            'created',
            'modified'
        )

    def clean(self):
        """Validation checks
        1. If given, check that maxCmeMonth < maxCmeYear
        2. If plan_type is Enterprise, then Org should be selected
        3. If Organization is selected: org should be assigned to only 1 active
            plan (of the given plan_type) at any time
        4. If welcome_offer_url is given, check that it exists as a valid AllowedUrl.
        """
        cleaned_data = super(PlanForm, self).clean()
        maxCmeMonth = cleaned_data.get('maxCmeMonth')
        maxCmeYear = cleaned_data.get('maxCmeYear')
        plan_type = cleaned_data.get('plan_type')
        org = cleaned_data.get('organization')
        welcome_offer_url = cleaned_data.get('welcome_offer_url')
        if maxCmeYear and maxCmeMonth and (maxCmeMonth >= maxCmeYear):
            self.add_error('maxCmeMonth', 'maxCmeMonth must be strictly less than maxCmeYear.')
        if maxCmeYear == 0 and maxCmeMonth != 0:
            self.add_error('maxCmeMonth', 'If maxCmeYear=0, then maxCmeMonth must also be 0 (for unlimited CME).')
        pt_ent = SubscriptionPlanType.objects.get(name=SubscriptionPlanType.ENTERPRISE)
        if plan_type == pt_ent and org is None:
            self.add_error('organization', 'Organization must be selected for Enterprise plan_type')
        if org is not None and self.instance and not self.instance.pk:
            # for new plan: check that org is assigned to only 1 active plan
            qs = SubscriptionPlan.objects.filter(organization=org, plan_type=plan_type, active=True).order_by('-pk')
            if qs.exists():
                p = qs[0]
                self.add_error('organization', 'This Organization is already assigned to active {0.plan_type} plan: {0.name}.'.format(p))
        if welcome_offer_url:
            # check it exists as a valid AllowedUrl
            qs = AllowedUrl.objects.filter(url=welcome_offer_url)
            if not qs.exists():
                self.add_error('welcome_offer_url', 'Enter this url into AllowedUrl first. Be sure to specify the pageTitle and DOI.')
            else:
                aurl = qs[0]
                if not aurl.valid:
                    self.add_error('welcome_offer_url', 'This url exists as an invalid AllowedUrl. Go to AllowedUrl and reset its valid flag first.')

    def save(self, commit=True):
        """Auto assign planId based on plan name and hashid of next id"""
        m = super(PlanForm, self).save(commit=False)
        if not m.planId:
            m.planId = SubscriptionPlan.objects.makePlanId(m.name)
        m.save()
        return m

class PlantagForm(forms.ModelForm):
    class Meta:
        model = Plantag
        fields = ('__all__')
        widgets = {
            'tag': autocomplete.ModelSelect2(
                url='cmetag-autocomplete',
                attrs={
                    'data-placeholder': 'CmeTag',
                    'data-minimum-input-length': 1,
                }
            ),
        }

class PlantagInline(admin.TabularInline):
    model = Plantag
    form = PlantagForm

class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('id',
        'plan_type',
        'plan_key',
        'planId',
        'name',
        'display_name',
        'price',
        'monthlyPrice',
        'organization',
        'is_public',
        'maxCmeYear',
        'billingCycleMonths',
        'formatTags'
    )
    list_select_related = True
    list_filter = ('active', 'is_public', 'plan_type', 'allowArticleSearch', 'plan_key', 'organization')
    ordering = ('plan_type', 'plan_key__name','price')
    filter_horizontal = ('tags',)
    form = PlanForm
    inlines = [
        PlantagInline,
    ]
    fieldsets = (
        (None, {
            'fields': ('plan_type', 'organization', 'plan_key','name','display_name', 'upgrade_plan','downgrade_plan'),
        }),
        ('Price', {
            'fields': ('price', 'discountPrice','displayMonthlyPrice')
        }),
        ('CME', {
            'fields': ('maxCmeYear','maxCmeMonth','max_trial_credits')
        }),
        ('Other', {
            'fields': ('is_public', 'trialDays','billingCycleMonths', 'allowArticleSearch', 'allowProfileStateTags', 'active', 'welcome_offer_url')
        })
    )

    def get_queryset(self, request):
        qs = super(SubscriptionPlanAdmin, self).get_queryset(request)
        return qs.prefetch_related('tags')

class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'subscriptionId', 'user', 'plan', 'status', 'display_status',
        'billingStartDate', 'billingEndDate', 'billingCycle', 'nextBillingAmount')
    list_select_related = ('user','plan')
    list_filter = ('status', 'display_status', UserFilter, 'plan')
    ordering = ('-modified',)
    actions = ('terminal_cancel',)
    class Media:
        pass

    def get_actions(self, request):
        """Remove default bulk-delete operation since it does not know about BT. All subs should be in sync w. BT"""
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def terminal_cancel(self, request, queryset):
        userid = request.GET.get('user__id__exact', None)
        #print('userid: {0}'.format(userid))
        if not userid or len(queryset) != 1:
            errmsg = 'First select a single user from the user dropdown, and then select one Braintree subscription to cancel'
            self.message_user(request, errmsg, level=messages.ERROR)
            return
        user_subs = queryset[0]
        # check this is a paid subs
        if not user_subs.plan.isPaid():
            errmsg = 'The subscription {0.subscriptionId} for {0.user} has plan_type: {0.plan.plan_type} (cannot be canceled by Braintree).'.format(user_subs)
            self.message_user(request, errmsg, level=messages.ERROR)
            return
        # check status
        if user_subs.status in (UserSubscription.CANCELED, UserSubscription.EXPIRED):
            errmsg = 'The subscription {0.subscriptionId} for {0.user} is already in status: {0.status}.'.format(user_subs)
            self.message_user(request, errmsg, level=messages.ERROR)
            return
        # process with terminal cancel
        res = UserSubscription.objects.terminalCancelBtSubscription(user_subs)
        if res.is_success:
            msg = 'The subscription {0.subscriptionId} for {0.user} has been canceled.'.format(user_subs)
            self.message_user(request, msg, level=messages.SUCCESS)
        else:
            errmsg = 'Cancel subscription {0.subscriptionId} Braintree error: {1.message}.'.format(user_subs, res.message)
            self.message_user(request, errmsg, level=messages.ERROR)
    terminal_cancel.short_description = 'Select single user and then select one subscription to cancel'

class SubscriptionEmailAdmin(admin.ModelAdmin):
    list_display = ('id', 'subscription', 'billingCycle', 'remind_renew_sent', 'expire_alert_sent')
    list_select_related = ('subscription',)
    ordering = ('-modified',)

class SubscriptionTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'transactionId', 'subscription', 'trans_type', 'amount', 'status', 'card_type', 'card_last4', 'receipt_sent', 'created', 'modified')
    list_select_related = ('subscription',)
    raw_id_fields = ('subscription',)
    list_filter = ('receipt_sent',)
    ordering = ('-modified',)


class CertificateAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'referenceId', 'tag','name', 'startDate', 'endDate', 'credits', 'created')
    list_select_related = ('user',)
    search_fields = ['referenceId',]
    list_filter = (UserFilter, 'tag')
    ordering = ('-created',)

    class Media:
        pass

class AuditReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'referenceId', 'name', 'startDate', 'endDate', 'created')
    list_select_related = ('user',)
    list_filter = (UserFilter,)
    search_fields = ['referenceId',]
    ordering = ('-created',)

    class Media:
        pass


class BatchPayoutAdmin(admin.ModelAdmin):
    list_display = ('id','sender_batch_id','payout_batch_id','status','amount','date_completed','modified')
    list_filter = ('status',)
    ordering = ('-modified',)

class AffiliatePayoutAdmin(admin.ModelAdmin):
    list_display = ('convertee','affiliate','status','payoutItemId','transactionId','amount','modified')
    list_select_related = True
    list_filter = ('status',)
    ordering = ('-modified',)

class CmeBoostAdmin(admin.ModelAdmin):
    list_display = ('id','name','credits','price','active','created')
    list_filter = ('active',)
    ordering = ('id',)

class CmeBoostPurchaseAdmin(admin.ModelAdmin):
    list_display = ('id','trans_type', 'user','boost','transactionId','amount','status','receipt_sent','created')
    list_filter = ('receipt_sent','failure_alert_sent', 'boost')
    ordering = ('-modified',)

class UserCmeCreditAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan_credits', 'boost_credits', 'total_credits_earned', 'modified')
    ordering = ('-modified',)
    list_filter = (UserFilter,)

    class Media:
        pass

#
# plugin models
#
class ProxyPatternAdmin(admin.ModelAdmin):
    list_display = ('id', 'proxyname', 'delimiter', 'created', 'modified')

class AllowedHostAdmin(admin.ModelAdmin):
    list_display = ('id', 'hostname', 'is_secure', 'description', 'has_paywall', 'allow_page_download', 'accept_query_keys', 'created')
    ordering = ('hostname',)
    list_filter = ('is_secure',)

class HostPatternAdmin(admin.ModelAdmin):
    list_display = ('id', 'host', 'eligible_site', 'pattern_key', 'path_contains', 'path_reject')
    list_select_related = ('host','eligible_site')
    list_filter = (EligibleSiteFilter, 'host')

    class Media:
        pass

class UrlTagFreqForm(forms.ModelForm):
    class Meta:
        model = UrlTagFreq
        fields = ('__all__')
        widgets = {
            'tag': autocomplete.ModelSelect2(
                url='cmetag-autocomplete',
                attrs={
                    'data-placeholder': 'CmeTag',
                    'data-minimum-input-length': 1,
                }
            ),
            'url': autocomplete.ModelSelect2(
                url='aurl-autocomplete',
                attrs={
                    'data-placeholder': 'Url',
                    'data-minimum-input-length': 8,
                }
            ),
        }

    def save(self, commit=True):
        """Sync AllowedUrl.numOffers to UrlTagFreq.numOffers if current value is less"""
        m = super(UrlTagFreqForm, self).save(commit=False) # save w.o commit to get obj
        aurl = m.url
        if aurl.numOffers < m.numOffers:
            aurl.numOffers = m.numOffers
            aurl.save(update_fields=('numOffers',))
        m.save() # final save. This is done to prevent object has no attribute 'save_m2m' error.
        return m

class UrlTagFreqInline(admin.StackedInline):
    model = UrlTagFreq
    extra = 1
    form = UrlTagFreqForm

class AllowedUrlAdmin(admin.ModelAdmin):
    list_display = ('id', 'eligible_site', 'url', 'valid', 'set_id', 'modified')
    list_select_related = ('host', 'eligible_site')
    list_filter = ('valid',EligibleSiteFilter, 'host',)
    filter_horizontal = ('cmeTags',)
    search_fields = ['page_title','set_id']
    ordering = ('-modified',)
    inlines = [
        UrlTagFreqInline,
    ]

    class Media:
        pass

class UrlTagFreqAdmin(admin.ModelAdmin):
    list_display = ('id','url','page_title', 'tag', 'numOffers')
    list_selected_related = ('tag','url')
    list_filter = (TagFilter,)
    ordering = ('-numOffers', '-modified',)
    form = UrlTagFreqForm

    def page_title(self, obj):
        return obj.url.page_title

    class Media:
        pass

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
    num_users.short_description = 'Num requesters'
    num_users.admin_order_field = 'num_users'

class ActivitySetAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'url', 'total_tracking_seconds', 'engaged_seconds', 'created')
    raw_id_fields = ('url',)
    readonly_fields = ('user','url','total_tracking_seconds',)
    list_filter = (UserFilter, )
    ordering = ('-created',)

    class Media:
        pass

    def engaged_seconds(self, obj):
        return obj.computed_value
    engaged_seconds.short_description = 'Engaged Seconds'
    engaged_seconds.admin_order_field = 'computed_value'

class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'url', 'x_tracking_seconds', 'num_highlight', 'num_mouse_click', 'num_mouse_move', 'num_start_scroll', 'created')
    raw_id_fields = ('activity_set',)
    readonly_fields = ('activity_set','num_highlight','num_mouse_click','num_mouse_move','num_start_scroll')
    ordering = ('-created',)

    def get_queryset(self, request):
        qs = super(ActivityLogAdmin, self).get_queryset(request)
        return qs.select_related('activity_set')

    def user(self, obj):
        return str(obj.activity_set.user)

    def url(self, obj):
        return str(obj.activity_set.url)

class RecAllowedUrlForm(forms.ModelForm):
    class Meta:
        model = RecAllowedUrl
        fields = ('__all__')
        widgets = {
            'user': autocomplete.ModelSelect2(
                url='useremail-autocomplete',
                attrs={
                    'data-placeholder': 'User',
                    'data-minimum-input-length': 2,
                }
            ),
            'url': autocomplete.ModelSelect2(
                url='aurl-autocomplete',
                attrs={
                    'data-placeholder': 'Url',
                    'data-minimum-input-length': 8,
                }
            ),
            'cmeTag': autocomplete.ModelSelect2(
                url='cmetag-autocomplete',
                attrs={
                    'data-placeholder': 'CmeTag',
                    'data-minimum-input-length': 1,
                }
            ),
        }

    def clean(self):
        cleaned_data = super(RecAllowedUrlForm, self).clean()
        user = cleaned_data.get('user')
        aurl = cleaned_data.get('url')
        #print('Checking {0} for {1}'.format(user, aurl))
        now = timezone.now()
        startdate = now - timedelta(days=OFFER_LOOKBACK_DAYS)
        filter_kwargs = dict(
            user=user,
            url=aurl,
            redeemed=True,
            valid=True,
            activityDate__gte=startdate,
        )
        if OrbitCmeOffer.objects.filter(**filter_kwargs).exists():
            # user has redeemed this url within OFFER_LOOKBACK_DAYS
            self.add_error('url', 'User has already redeemed this url')

class RecAllowedUrlAdmin(admin.ModelAdmin):
    list_display = ('id','user','cmeTag','url', 'offerid')
    list_select_related = True
    raw_id_fields = ('offer',)
    list_filter = (UserFilter, CmeTagFilter)
    ordering = ('user', 'url')
    form = RecAllowedUrlForm

    def offerid(self, obj):
        return obj.offer.pk if obj.offer else None

    class Media:
        pass

class OrbitCmeOfferAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'activityDate', 'redeemed', 'url', 'suggestedDescr', 'valid', 'lastModified')
    #list_display = ('id', 'user', 'activityDate', 'redeemed', 'url', 'formatTags', 'lastModified')
    list_select_related = True
    ordering = ('-modified',)
    list_filter = ('redeemed','valid', UserFilter, 'eligible_site')
    filter_horizontal = ('tags', 'selectedTags')

    class Media:
        pass

    def lastModified(self, obj):
        return fmtLocalDatetime(obj.modified)
    lastModified.short_description = 'Modified'
    lastModified.admin_order_field = 'modified'

class HashTagAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'description', 'formatSpecialties', 'formatSubSpecialties')
    ordering = ('code',)
    filter_horizontal = ('specialties', 'subspecialties')


class InfluencerGroupAdmin(admin.ModelAdmin):
    list_display = ('id','name','twitter_handle','tweet_template')
    ordering = ('name',)

class InfluencerMembershipForm(forms.ModelForm):
    class Meta:
        model = InfluencerMembership
        fields = ('__all__')
        widgets = {
            'user': autocomplete.ModelSelect2(
                url='useremail-autocomplete',
                attrs={
                    'data-placeholder': 'User',
                    'data-minimum-input-length': 2,
                }
            ),
        }

class InfluencerMembershipAdmin(admin.ModelAdmin):
    list_display = ('id','group','user','created')
    list_filter = ('group', UserFilter)
    ordering = ('-created',)
    form = InfluencerMembershipForm

    class Media:
        pass

# register models
admin_site.register(Affiliate, AffiliateAdmin)
admin_site.register(AffiliateDetail, AffiliateDetailAdmin)
admin_site.register(AffiliatePayout, AffiliatePayoutAdmin)
admin_site.register(AuthImpersonation, AuthImpersonationAdmin)
admin_site.register(AuditReport, AuditReportAdmin)
admin_site.register(BatchPayout, BatchPayoutAdmin)
admin_site.register(Certificate, CertificateAdmin)
admin_site.register(CmeBoost, CmeBoostAdmin)
admin_site.register(CmeBoostPurchase, CmeBoostPurchaseAdmin)
admin_site.register(CmeTag, CmeTagAdmin)
admin_site.register(Country, CountryAdmin)
admin_site.register(CreditType, CreditTypeAdmin)
admin_site.register(Customer, CustomerAdmin)
admin_site.register(Degree, DegreeAdmin)
admin_site.register(Discount, DiscountAdmin)
admin_site.register(SignupDiscount, SignupDiscountAdmin)
admin_site.register(SignupEmailPromo, SignupEmailPromoAdmin)
admin_site.register(Document, DocumentAdmin)
admin_site.register(EligibleSite, EligibleSiteAdmin)
admin_site.register(Entry, EntryAdmin)
admin_site.register(EntryType, EntryTypeAdmin)
admin_site.register(Hospital, HospitalAdmin)
admin_site.register(InvitationDiscount, InvitationDiscountAdmin)
admin_site.register(LicenseType, LicenseTypeAdmin)
admin_site.register(Organization, OrgAdmin)
admin_site.register(OrgAgg, OrgAggAdmin)
admin_site.register(OrgFile, OrgFileAdmin)
admin_site.register(OrgMember, OrgMemberAdmin)
admin_site.register(OrgEnrollee, OrgEnrolleeAdmin)
admin_site.register(OrgReport, OrgReportAdmin)
admin_site.register(Profile, ProfileAdmin)
admin_site.register(PracticeSpecialty, PracticeSpecialtyAdmin)
admin_site.register(ResidencyProgram, ResidencyProgramAdmin)
admin_site.register(Sponsor, SponsorAdmin)
admin_site.register(State, StateAdmin)
admin_site.register(StateLicense, StateLicenseAdmin)
admin_site.register(UserFeedback, UserFeedbackAdmin)
admin_site.register(SubscriptionEmail, SubscriptionEmailAdmin)
admin_site.register(SubscriptionPlan, SubscriptionPlanAdmin)
admin_site.register(SubscriptionPlanKey, SubscriptionPlanKeyAdmin)
admin_site.register(SubscriptionPlanType, SubscriptionPlanTypeAdmin)
admin_site.register(SubscriptionTransaction, SubscriptionTransactionAdmin)
admin_site.register(SubSpecialty, SubSpecialtyAdmin)
admin_site.register(UserCmeCredit, UserCmeCreditAdmin)
admin_site.register(UserSubscription, UserSubscriptionAdmin)
#
# social models
#
admin_site.register(HashTag, HashTagAdmin)
admin_site.register(InfluencerGroup, InfluencerGroupAdmin)
admin_site.register(InfluencerMembership, InfluencerMembershipAdmin)
#
# plugin models
#
admin_site.register(AllowedHost, AllowedHostAdmin)
admin_site.register(HostPattern, HostPatternAdmin)
admin_site.register(AllowedUrl, AllowedUrlAdmin)
admin_site.register(RejectedUrl, RejectedUrlAdmin)
admin_site.register(RequestedUrl, RequestedUrlAdmin)
admin_site.register(ActivitySet, ActivitySetAdmin)
admin_site.register(ActivityLog, ActivityLogAdmin)
admin_site.register(RecAllowedUrl, RecAllowedUrlAdmin)
admin_site.register(UrlTagFreq, UrlTagFreqAdmin)
admin_site.register(OrbitCmeOffer, OrbitCmeOfferAdmin)
admin_site.register(ProxyPattern, ProxyPatternAdmin)
