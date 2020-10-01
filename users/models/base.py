from __future__ import unicode_literals
from collections import OrderedDict
import logging
from datetime import datetime, timedelta
from hashids import Hashids
import pytz
import re
from dateutil.relativedelta import *
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from django.contrib.postgres.search import SearchVector
from django.db import models
from django.db.models import Q, Subquery
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property
from django.db import transaction
from common.appconstants import (
    GROUP_ENTERPRISE_ADMIN,
    GROUP_ENTERPRISE_MEMBER,
    GROUP_ARTICLEHISTORY,
    GROUP_ARTICLESEARCH,
    GROUP_ARTICLEDDX
)
logger = logging.getLogger('gen.models')

#
# constants (should match the database values)
#
CMETAG_SACME = 'SAM/SA-CME'
# Physician specialties that have SA-CME tag pre-selected on OrbitCmeOffer
SACME_SPECIALTIES = (
    'Radiology',
    'Radiation Oncology',
    'Osteopathic Radiology',
    'Pathology',
    'Opthamology'
)
# Physician specialties eligible for ABIM MOC Points
ABIM_MOC_SPECIALTIES = (
    'Internal Medicine',
)
TEST_CARD_EMAIL_PATTERN = re.compile(r'testcode-(?P<code>\d+)')
HASHIDS_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890!@' # extend alphabet with ! and @

ACTIVE_OFFDATE = datetime(3000,1,1,tzinfo=pytz.utc)

# Q objects
Q_ADMIN = Q(username__in=('admin','radmin')) # django admin users not in auth0
Q_IMPERSONATOR = Q(is_staff=True) & ~Q_ADMIN

def default_expire():
    """Used by AuthImpersonation"""
    return timezone.now() + timedelta(seconds=3600)

@python_2_unicode_compatible
class AuthImpersonation(models.Model):
    """A way for an admin user to enable impersonate of a particular user for a fixed time period. This model is used by ImpersonateBackend."""
    impersonator = models.ForeignKey(User,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='impersonators',
        # staff users only (and exclude django-only admin users)
        limit_choices_to=Q_IMPERSONATOR
    )
    impersonatee = models.ForeignKey(User,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='impersonatees'
    )
    expireDate = models.DateTimeField(default=default_expire)
    valid = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)


    def __str__(self):
        return '{0.email}/{1.email}'.format(
                self.impersonator, self.impersonatee)


class CmeTagCategory(models.Model):
    name= models.CharField(max_length=80, unique=True, help_text='Category name.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = 'CME Tag Categories'
        ordering = ['name',]

class CmeTagManager(models.Manager):
    def getSpecTags(self):
        pspecs = PracticeSpecialty.objects.all()
        pnames = [p.name for p in pspecs]
        tags = self.model.objects.filter(name__in=pnames)
        return tags

@python_2_unicode_compatible
class CmeTag(models.Model):
    ABA_EVENTID_MAX_CHARS = 10 # Max number of characters to construct ABA EventId from tag name
    # named tags used by various methods
    FLUOROSCOPY = 'Fluoroscopy'
    RADIATION_SAFETY = 'Radiation Safety'
    SACME = 'SAM/SA-CME'
    ABIM_MOC = 'MOC Points (ABIM)'

    # fields
    name = models.CharField(max_length=80, unique=True, help_text='Short-form name. Used in tag button')
    abbrev =  models.CharField(max_length=4, blank=True, default='', help_text='Abbreviation used in ABA EventId')
    priority = models.IntegerField(
        default=2,
        help_text='Used for non-alphabetical sort. 0=Specialty-name tag. 1=SA-CME. 2=Others.'
    )
    description = models.CharField(max_length=200, unique=True, help_text='Long-form name. Must be unique. Used on certificates.')
    srcme_only = models.BooleanField(default=False,
            help_text='True if tag is only valid for self-reported cme')
    exemptFrom1Tag = models.BooleanField(default=False,
            help_text='True if tag is exempt from the 1-tag-only policy on redeeming offers.')
    instructions = models.TextField(default='', help_text='Instructions to provider. May contain Markdown-formatted text.')
    category = models.ForeignKey(CmeTagCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name='tags',
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = CmeTagManager()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = 'CME Tags'
        ordering = ['priority', 'name']


@python_2_unicode_compatible
class Country(models.Model):
    """Names of countries for country of practice."""
    USA = 'USA'
    # fields
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=5, blank=True, help_text='ISO Alpha-3 code')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    class Meta:
        verbose_name_plural = 'Countries'


@python_2_unicode_compatible
class State(models.Model):
    """Names of states/provinces within a country.
    """
    country = models.ForeignKey(Country,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='states',
    )
    name = models.CharField(max_length=100)
    abbrev = models.CharField(max_length=15, blank=True)
    rnCertValid = models.BooleanField(default=False, help_text='True if RN/NP certificate is valid in this state')
    cmeTags = models.ManyToManyField(CmeTag,
        blank=True,
        related_name='states',
        help_text='cmeTags to be added to profile for users who select this state'
    )
    deaTags = models.ManyToManyField(CmeTag,
        through='StateDeatag',
        blank=True,
        related_name='deastates',
        help_text='cmeTags to be added to profile for users with DEA licenses'
    )
    doTags = models.ManyToManyField(CmeTag,
        blank=True,
        related_name='dostates',
        help_text='cmeTags to be added to profile for users with DO degree'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['country','name']
        unique_together = (('country', 'name'), ('country', 'abbrev'))

    def __str__(self):
        return self.name

    def formatTags(self):
        return ", ".join([t.name for t in self.cmeTags.all()])
    formatTags.short_description = "cmeTags"

    def formatDEATags(self):
        return ", ".join([t.name for t in self.deaTags.all()])
    formatDEATags.short_description = "deaTags"

    def formatDOTags(self):
        return ", ".join([t.name for t in self.doTags.all()])
    formatDOTags.short_description = "doTags"

# Many-to-many through relation between State and CmeTag for DEA
class StateDeatag(models.Model):
    state = models.ForeignKey(State, on_delete=models.CASCADE, db_index=True)
    tag = models.ForeignKey(CmeTag, on_delete=models.CASCADE)
    dea_in_state = models.BooleanField(default=True,
        help_text='True if user needs DEA license in this particular state. False if any state')

    class Meta:
        unique_together = ('state','tag')
        ordering = ['tag',]

    def __str__(self):
        return '{0.state}|{0.tag}'.format(self)



class HospitalManager(models.Manager):

    def search_filter(self, search_term, base_qs=None):
        """Returns a queryset that filters for the given search_term
        """
        if not base_qs:
            base_qs = self.model.objects.all()
        s = search_term.upper()
        qs1 = base_qs.filter(display_name__startswith=s)
        qs2 = base_qs.filter(display_name__contains=s)
        qs = qs1
        if not qs.exists():
            qs = qs2
        return qs.order_by('display_name')

    def alt_search_filter(self, search_term, base_qs=None):
        """Returns a queryset that filters for the given search_term
        Uses: django.contrib.postgres SearchVector
        """
        if not base_qs:
            base_qs = self.model.objects.select_related('state')
        qs_all = base_qs.annotate(
                search=SearchVector('name','city', 'state__name', 'state__abbrev')).all()
        qset = qs_all.filter(search=search_term)
        return qset.order_by('name','city')


@python_2_unicode_compatible
class Hospital(models.Model):
    state = models.ForeignKey(State,
        on_delete=models.CASCADE,
        related_name='hospitals',
        db_index=True
    )
    name = models.CharField(max_length=120, db_index=True)
    display_name = models.CharField(max_length=200, help_text='UPPERCASE. Used for search and display')
    city = models.CharField(max_length=80, db_index=True)
    website = models.URLField(max_length=500, blank=True)
    county = models.CharField(max_length=60, blank=True)
    hasResidencyProgram = models.BooleanField(default=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = HospitalManager() # default manager

    def __str__(self):
        return self.display_name

    def str_long(self):
        return "{0.pk}|{0.display_name}|{0.city}|{0.state.abbrev}".format(self)

    class Meta:
        ordering = ['name',]
        unique_together = ('state','city','name')

class ResidencyProgramManager(models.Manager):
    def search_filter(self, search_term, base_qs=None):
        """Returns a queryset that filters for the given search_term
        """
        if not base_qs:
            base_qs = self.model.objects.all()
        qs1 = base_qs.filter(name__istartswith=search_term)
        qs2 = base_qs.filter(name__icontains=search_term)
        qs = qs1
        if not qs.exists():
            qs = qs2
        return qs.order_by('name')

@python_2_unicode_compatible
class ResidencyProgram(models.Model):
    name = models.CharField(max_length=120, unique=True, db_index=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = ResidencyProgramManager()

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name',]

class DegreeManager(models.Manager):
    def insertDegreeAfter(self, from_deg, abbrev, name):
        """Insert new degree after the given from_deg
        and update sort_order of the items that need to be shuffled down.
        """
        new_deg = None
        # make a hole
        post_degs = Degree.objects.filter(sort_order__gt=from_deg.sort_order).order_by('sort_order')
        with transaction.atomic():
            for m in post_degs:
                m.sort_order += 1
                m.save()
            new_sort_order = from_deg.sort_order + 1
            logger.info('Adding new Degree {0} at sort_order: {1}'.format(abbrev, new_sort_order))
            new_deg = Degree.objects.create(abbrev=abbrev, name=name, sort_order=new_sort_order)
        return new_deg

@python_2_unicode_compatible
class Degree(models.Model):
    """Names and abbreviations of professional roles"""
    MD = 'MD'
    DO = 'DO'
    NP = 'NP'
    RN = 'RN'
    PA = 'PA'
    OTHER = 'Other'
    abbrev = models.CharField(max_length=7, unique=True)
    name = models.CharField(max_length=40)
    sort_order = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = DegreeManager()

    def __str__(self):
        return self.abbrev

    def isVerifiedForCme(self):
        """Returns True if verified for CME"""
        abbrev = self.abbrev
        return abbrev == Degree.MD or abbrev == Degree.DO

    def isNurse(self):
        """Returns True if RN/NP"""
        abbrev = self.abbrev
        return abbrev == Degree.RN or abbrev == Degree.NP

    def isPhysician(self):
        """Returns True if MD/DO"""
        abbrev = self.abbrev
        return abbrev == Degree.MD or abbrev == Degree.DO

    class Meta:
        ordering = ['sort_order',]


@python_2_unicode_compatible
class PracticeSpecialty(models.Model):
    """Names of practice specialties.
    """
    ANESTHESIOLOGY = 'Anesthesiology'
    INT_MED = 'Internal Medicine'
    # fields
    name = models.CharField(max_length=100, unique=True)
    cmeTags = models.ManyToManyField(CmeTag,
        blank=True,
        related_name='specialties',
        help_text='Eligible cmeTags for this specialty'
    )
    is_abms_board = models.BooleanField(default=False, help_text='True if this is an ABMS Board/General Cert')
    is_primary = models.BooleanField(default=False, help_text='True if this is a Primary Specialty Certificate')
    planText = models.CharField(max_length=500, blank=True, default='',
            help_text='Default response for changes to clinical plan')
    internalSearchEngineid = models.CharField(max_length=50, blank=True, default='',
            help_text='Internal Google search engine ID to use for categorizing articles in this specialty. Used for ddx/studytopic assignment. Must match a valid ID defined in the google console.')
    userSearchEngineid = models.CharField(max_length=50, blank=True, default='',
            help_text='Public Google search engine ID to use for the RelatedArticleRail for users in this specialty. Must match a valid ID defined in the google console.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def formatTags(self):
        return ", ".join([t.name for t in self.cmeTags.all()])
    formatTags.short_description = "cmeTags"

    def formatSubSpecialties(self):
        return ", ".join([t.name for t in self.subspecialties.all()])
    formatSubSpecialties.short_description = "SubSpecialties"

    class Meta:
        verbose_name_plural = 'Practice Specialties'

@python_2_unicode_compatible
class SubSpecialty(models.Model):
    specialty = models.ForeignKey(PracticeSpecialty,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='subspecialties',
    )
    name = models.CharField(max_length=60)
    cmeTags = models.ManyToManyField(CmeTag,
        blank=True,
        related_name='subspecialties',
        help_text='Applicable cmeTags'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{0.name} in {0.specialty}".format(self)

    def formatTags(self):
        return ", ".join([t.name for t in self.cmeTags.all()])
    formatTags.short_description = "cmeTags"

    class Meta:
        verbose_name_plural = 'Practice Sub Specialties'
        unique_together = ('specialty', 'name')
        ordering = ['name',]

class OrganizationManager(models.Manager):
    def getOrgForEmail(self, email):
        L = email.split('@')
        if len(L) != 2:
            return None
        ed = L[1].lower()
        qs = self.model.objects.filter(email_domain=ed).order_by('-created')
        if qs.exists():
            return qs[0]
        return None

@python_2_unicode_compatible
class Organization(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True, help_text='Org short code (ASCII only - used to create joinCode for command-line arguments)')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    credits = models.FloatField(default=0,
            help_text='Computed total credits earned by this org since creditStartDate until today.')
    creditStartDate = models.DateTimeField(null=True, blank=True,
            help_text='Start date of total credits calculation')
    creditEndDate = models.DateTimeField(null=True, blank=True,
            help_text='End date of total credits calculation')
    joinCode = models.CharField(max_length=20, default='',
            help_text='Join Code for invitation URL')
    providerStat = JSONField(default=dict, blank=True)
    # Note: if value is changed to False after usergoals are created, a manual command must be run to delete the usergoals.
    # Likewise, if value is changed to True after members already exist, a manual command must be run to assign them usergoals.
    activateGoals = models.BooleanField(default=True,
            help_text='If True: goal compliance checking is enabled for members of this enterprise org.')
    # Added 2020-02-04: new users with an email domain matching org's email_domain are considered members
    email_domain = models.CharField(max_length=40, blank=True, default='',
        help_text='A new individual user is made a member of this org if their email_domain matches this value. e.g. radpartners.com')
    computeTeamStats = models.BooleanField(default=True,
            help_text='If True: provider stats will be computed daily. Set to False if org is not an active Enterprise org.')
    objects = OrganizationManager()
 
    def __str__(self):
        return self.code

    def getEnterprisePlan(self):
        """Find the latest Enterprise SubscriptionPlan for self
        Used by admin UI on ModelAdmin
        Returns: SubscriptionPlan or None
        """
        from .subscription import SubscriptionPlanType
        qs = self.plans.select_related('plan_type') \
            .filter(plan_type__name=SubscriptionPlanType.ENTERPRISE) \
            .order_by('-created')
        if qs.exists():
            return qs[0]
        return None

    def getAdvancedPlan(self):
        """Find the latest Advanced SubscriptionPlan for self
        Used by admin UI on ModelAdmin
        Returns: SubscriptionPlan or None
        """
        from .subscription import SubscriptionPlanType
        qs = self.plans.select_related('plan_type') \
            .filter(plan_type__name=SubscriptionPlanType.BRAINTREE, name__contains='Advanced') \
            .order_by('-created')
        if qs.exists():
            return qs[0]
        return None

    def computeCreditsEarned(self):
        """Compute and update self.credits and credit dates"""
        from .feed import Entry
        firstMember = self.orgmembers.all().order_by('created')[0]
        startDate = firstMember.created
        filter_kwargs = {
            'user__profile__organization': org,
            'valid': True
        }
        if self.creditEndDate:
            # if credits have been computed before, then just add credits from entries created since the last calculation
            filter_kwargs['created__gt'] = self.creditEndDate
        entries = Entry.objects \
            .select_related('entryType', 'user__profile') \
            .filter(**filter_kwargs) \
            .order_by('id')
        credits = 0
        doSave = False
        now = timezone.now()
        for entry in entries:
            credits += entry.getCredits()
        credits = float(credits)
        if credits:
            self.credits += credits
            self.creditEndDate = now
            doSave = True
        if not self.creditStartDate:
            self.creditStartDate = startDate
            doSave = True
        if doSave:
            self.save(update_fields=('credits', 'creditStartDate', 'creditEndDate'))
            logger.info('Org {0.code} credits {0.credits} until EndDate: {0.creditEndDate}'.format(self))

    def computeProviderStats(self):
        """Update self.providerStats: current vs end-of-prior-month"""
        providerStat = dict()
        degrees = Degree.objects.all()
        for d in degrees:
            providerStat[d.abbrev] = {'count': 0, 'lastCount': 0, 'diff': 0}
        # filter out pending org users
        members = self.orgmembers.filter(removeDate__isnull=True, pending=False)
        # Per request of Ram: do not exclude unverified profiles.
        profiles = Profile.objects \
            .filter(user__in=Subquery(members.values('user'))) \
            .only('user','degrees') \
            .prefetch_related('degrees')
        for profile in profiles:
            if profile.degrees.exists():
                d = profile.degrees.all()[0]
                providerStat[d.abbrev]['count'] += 1
        # get datetime of end of last month
        cutoffDate = datetime(now.year, now.month, 1, 23, 59, 59, tzinfo=pytz.utc) - relativedelta(days=1)
        # members existing at that time
        members = self.orgmembers.filter(
            Q(removeDate__isnull=True) | Q(removeDate__gte=cutoffDate),
            created__lte=cutoffDate,
            pending=False
        )
        profiles = Profile.objects \
            .filter(user__in=Subquery(members.values('user'))) \
            .only('user','degrees') \
            .prefetch_related('degrees')
        for profile in profiles:
            if profile.degrees.exists(): # need this check otherwise get IndexError on next line if profile has no degrees
                d = profile.degrees.all()[0]
                providerStat[d.abbrev]['lastCount'] += 1
        # calculate diff percentage
        for abbrev in providerStat:
            count = providerStat[abbrev]['count']
            lastCount = providerStat[abbrev]['lastCount']
            diff = 0
            if lastCount:
                diff = (count - lastCount)*1.0/lastCount
            else:
                diff = count
            providerStat[abbrev]['diff'] = diff*100
        self.providerStat = providerStat
        self.save(update_fields=('providerStat',))
        logger.info('Updated providerStat for org {0}'.format(org))

def orgfile_document_path(instance, filename):
    """Used as the OrgFile document FileField upload_to value
    Note: tried moving it to same file as OrgFile but it resulted in
    a migration error
    """
    return '{0}/org_{1}/{2}'.format(settings.ORG_MEDIA_BASEDIR, instance.organization.id, filename)


class ProfileManager(models.Manager):

    def createProfile(self, user, socialId, planId):
        """Create Profile instance for the given user
        This is called auth_backeds.signup_user
        """
        hashgen = Hashids(salt=settings.HASHIDS_SALT, alphabet=HASHIDS_ALPHABET, min_length=5)
        profile = Profile.objects.create(
            user=user,
            inviteId=hashgen.encode(user.pk),
            planId=planId,
            socialId=socialId
        )
        return profile

    def createUserAndProfile(self, email, planId, inviter=None, affiliateId='', socialId='', pictureUrl='', verified=False, organization=None, firstName='', lastName=''):
        """Create new User instance and new Profile instance"""
        user = User.objects.create(
            username=email,
            email=email
        )
        profile = Profile.objects.create(
            user=user,
            inviteId=hashgen.encode(user.pk),
            planId=planId,
            inviter=inviter,
            affiliateId=affiliateId,
            socialId=socialId,
            pictureUrl=pictureUrl,
            verified=verified,
            organization=organization,
            firstName=firstName,
            lastName=lastName
            )
        return profile

    def groupActiveTagsByCatg(self, profile):
        """Group the user's active ProfileCmeTags by CmeTagCategory
        Returns: OrderedDict: {CmeTagCategory instance => list of CmeTags}
        """
        pcts = ProfileCmetag.objects \
            .filter(profile=profile, is_active=True) \
            .select_related('tag__category') \
            .order_by('tag__category__name', 'tag__name')
        grouped = OrderedDict()
        for pct in pcts:
            tag = pct.tag
            catg = tag.category
            if catg not in grouped:
                grouped[catg] = []
            grouped[catg].append(tag)
        return grouped

    def getProfilesForABA(self):
        """Get profiles for American Board of Anesthesiology matching:
        Country=USA (MD or DO), specialty includes Anesthesiology, and non-blank ABANumber.
        Note: Some profiles returned may have inactive subscription - caller must filter out if needed.
        Returns: queryset
        """
        usa = Country.objects.get(code=Country.USA)
        ps_anes = PracticeSpecialty.objects.get(name=PracticeSpecialty.ANESTHESIOLOGY)
        deg_md = Degree.objects.get(abbrev=Degree.MD)
        deg_do = Degree.objects.get(abbrev=Degree.DO)
        Q_deg = Q(degrees=deg_md) | Q(degrees=deg_do)
        profiles = Profile.objects.filter(Q_deg, specialties=ps_anes, country=usa).exclude(ABANumber='').order_by('pk')
        return profiles

    def getProfilesForTuftsABIM(self):
        """Get profiles for ABIM reporting to Tufts.
        Country=USA (MD or DO), specialty includes INT_MED, and non-blank ABIMNumber/NPI/birthDate.
        Note: Some profiles returned may have inactive subscription - caller must filter out if needed.
        Returns: queryset
        """
        usa = Country.objects.get(code=Country.USA)
        ps_im = PracticeSpecialty.objects.get(name=PracticeSpecialty.INT_MED)
        deg_md = Degree.objects.get(abbrev=Degree.MD)
        deg_do = Degree.objects.get(abbrev=Degree.DO)
        Q_deg = Q(degrees=deg_md) | Q(degrees=deg_do)
        Q_reject = Q(ABIMNumber='') | Q(npiNumber='') | Q(birthDate__isnull=True)
        profiles = Profile.objects \
            .filter(Q_deg, specialties=ps_im, country=usa) \
            .exclude(Q_reject) \
            .order_by('pk')
        return profiles

    def allowArticleHistory(self, user, user_subs):
        """User belongs to ArticleHistory group OR plan.allowArticleHistory is True
        Args:
            user: User instance
            user_subs: UserSubscription instance (can be None)
        Returns bool - True if allowed, else False
        """
        if user_subs and user_subs.plan.allowArticleHistory:
            return True
        return user.groups.filter(name=GROUP_ARTICLEHISTORY).exists()

    def allowArticleSearch(self, user, user_subs):
        """User belongs to ArticleSearch group OR plan.allowArticleSearch is True
        Args:
            user: User instance
            user_subs: UserSubscription instance (can be None)
        Returns bool - True if allowed, else False
        """
        if user_subs and user_subs.plan.allowArticleSearch:
            return True
        return user.groups.filter(name=GROUP_ARTICLESEARCH).exists()

    def allowDdx(self, user, user_subs):
        """User belongs to Ddx group or plan.allowDdx is True
        Args:
            user: User instance
            user_subs: UserSubscription instance (can be None)
        Returns bool - True if allowed, else False
        """
        if user_subs and user_subs.plan.allowDdx:
            return True
        return user.groups.filter(name=GROUP_ARTICLEDDX).exists()

@python_2_unicode_compatible
class Profile(models.Model):
    user = models.OneToOneField(User,
        on_delete=models.CASCADE,
        primary_key=True
    )
    firstName = models.CharField(max_length=30)
    lastName = models.CharField(max_length=30)
    contactEmail = models.EmailField(blank=True)
    country = models.ForeignKey(Country,
        on_delete=models.PROTECT,
        db_index=True,
        related_name='profiles',
        null=True,
        blank=True,
        help_text='Primary country of practice'
    )
    inviter = models.ForeignKey(User,
        on_delete=models.SET_NULL,
        db_index=True,
        related_name='invites',
        null=True,
        blank=True,
        help_text='Set during profile creation to the user whose inviteId was provided upon first login.'
    )
    organization = models.ForeignKey(Organization,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
        blank=True,
        related_name='profiles'
    )
    residency = models.ForeignKey(Hospital,
        on_delete=models.SET_NULL,
        db_index=True,
        null=True,
        blank=True,
        related_name='hresidencies',
        help_text='Residency Program from Hospital [old]'
    )
    residency_program = models.ForeignKey(ResidencyProgram,
        on_delete=models.SET_NULL,
        db_index=True,
        null=True,
        blank=True,
        related_name='residencies',
        help_text='Residency Program'
    )
    birthDate = models.DateField(null=True, blank=True)
    residencyEndDate = models.DateField(null=True, blank=True,
            help_text='Date of completion of residency program')
    affiliationText = models.CharField(max_length=200, blank=True, default='',
            help_text='User specified affiliation')
    interestText = models.CharField(max_length=500, blank=True, default='',
            help_text='User specified interests')

    planId = models.CharField(max_length=36, blank=True, help_text='planId selected at signup')
    ABANumber = models.CharField(max_length=10, blank=True, help_text='ABA ID (American Board of Anesthesiology)')
    ABIMNumber = models.CharField(max_length=10, blank=True, help_text='ABIM ID (American Board of Internal Medicine)')
    npiNumber = models.CharField(max_length=20, blank=True, help_text='Professional ID')
    npiFirstName = models.CharField(max_length=30, blank=True, help_text='First name from NPI Registry')
    npiLastName = models.CharField(max_length=30, blank=True, help_text='Last name from NPI Registry')
    npiType = models.IntegerField(
        default=1,
        blank=True,
        choices=((1, 'Individual'), (2, 'Organization')),
        help_text='Type 1 (Individual). Type 2 (Organization).'
    )
    nbcrnaId = models.CharField(max_length=20, blank=True, default='', help_text='NBCRNA ID for Nurse Anesthetists')
    inviteId = models.CharField(max_length=36, unique=True)
    socialId = models.CharField(max_length=64, blank=True, db_index=True, help_text='Auth0 ID')
    pictureUrl = models.URLField(max_length=1000, blank=True, help_text='Auth0 avatar URL')
    cmeTags = models.ManyToManyField(CmeTag,
            through='ProfileCmetag',
            blank=True,
            related_name='profiles')
    degrees = models.ManyToManyField(Degree, blank=True) # called primaryrole in UI
    specialties = models.ManyToManyField(PracticeSpecialty, blank=True, related_name='profiles')
    subspecialties = models.ManyToManyField(SubSpecialty, blank=True, related_name='profiles')
    states = models.ManyToManyField(State, blank=True, related_name='profiles')
    hasDEA = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        default=None,
        choices=((0, 'No'), (1, 'Yes')),
        help_text='Does user have DEA registration. Value is 0, 1 or null for unset')
    deaStates = models.ManyToManyField(State, blank=True, related_name='dea_profiles')
    fluoroscopyStates = models.ManyToManyField(State, blank=True, related_name='fluoroscopy_profiles')
    hospitals = models.ManyToManyField(Hospital, blank=True, related_name='profiles')
    verified = models.BooleanField(default=False, help_text='User has verified their email via Auth0')
    is_affiliate = models.BooleanField(default=False, help_text='True if user is an approved affiliate')
    accessedTour = models.BooleanField(default=False, help_text='User has commenced the online product tour')
    syncDataToOrg = models.BooleanField(default=False, help_text='Used for indiv_subscriber OrgMember users to allow them to opt-in to share data wit the Org.')
    allowArticleSearch = models.BooleanField(default=False,
        help_text='Enable Related Article rail in plugin for this user.')
    cmeStartDate = models.DateTimeField(null=True, blank=True, help_text='Start date for CME requirements calculation')
    cmeEndDate = models.DateTimeField(null=True, blank=True, help_text='Due date for CME requirements fulfillment')
    affiliateId = models.CharField(max_length=20, blank=True, default='', help_text='If conversion, specify Affiliate ID')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = ProfileManager()

    def __str__(self):
        return '{0.firstName} {0.lastName}'.format(self)

    def getFullName(self):
        return "{0} {1}".format(self.firstName, self.lastName)

    def getFullNameAndDegree(self):
        degrees = self.degrees.all()
        degree_str = ", ".join(str(degree.abbrev) for degree in degrees)
        return "{0} {1}, {2}".format(self.firstName, self.lastName, degree_str)

    def formatABANumber(self):
        """Return ABANumber formatted as xxxx-xxxx"""
        if not self.ABANumber:
            return ''
        return "{0}-{1}".format(self.ABANumber[0:4], self.ABANumber[4:])

    def isEnterpriseAdmin(self):
        """Returns True if self.user.groups contains GROUP_ENTERPRISE_ADMIN, else False
        """
        qs  = self.user.groups.filter(name=GROUP_ENTERPRISE_ADMIN)
        return qs.exists()

    def isAnesthesiologist(self):
        """Returns True if specialties includes Anesthesiology"""
        return self.specialties.filter(name=PracticeSpecialty.ANESTHESIOLOGY).exists()

    def isIntMed(self):
        """Returns True if specialties includes INT_MED"""
        return self.specialties.filter(name=PracticeSpecialty.INT_MED).exists()

    def shouldReqNPINumber(self):
        """
        If (country=USA) and (MD or DO in self.degrees),
        then npiNumber should be requested
        """
        if self.country is None:
            return False
        us = Country.objects.get(code=Country.USA)
        if self.country.pk != us.pk:
            return False
        deg_abbrevs = [d.abbrev for d in self.degrees.all()]
        has_md = Degree.MD in deg_abbrevs
        if has_md:
            return True
        has_do = Degree.DO in deg_abbrevs
        if has_do:
            return True
        return False

    def shouldReqABANumber(self):
        """True if:
        Specialty includes Anesthesiology, and country is USA
        Per Ram 11/26/19: skip check if degree is MD/DO
        """
        if not self.isAnesthesiologist():
            return False
        if self.country is None:
            return False
        us = Country.objects.get(code=Country.USA)
        if self.country.pk != us.pk:
            return False
        return True

    def shouldReqABIMNumber(self):
        """True if: MD/DO, specialty includes INT_MED, and country is USA
        """
        if not self.isPhysician():
            return False
        if not self.isIntMed():
            return False
        if self.country is None:
            return False
        us = Country.objects.get(code=Country.USA)
        if self.country.pk != us.pk:
            return False
        return True

    def isProfileCompleteForMOC(self):
        if not self.shouldReqABIMNumber():
            return False
        if self.ABIMNumber and self.npiNumber and self.birthDate:
            return True
        return False

    def isNPIComplete(self):
        """Returns True if npiNumber/LastName/FirstName are populated if required"""
        if self.shouldReqNPINumber():
            if self.npiNumber and self.npiLastName and self.npiFirstName:
                return True # required and filled
            return False # required and not filled
        return True # not required

    def isSignupComplete(self):
        """Signup is complete if:
            1. User has entered first and last name
            2. user has saved a UserSubscription
        """
        if not self.firstName or not self.lastName or not self.user.subscriptions.exists():
            return False
        return True

    def isCompleteForGoals(self):
        """Returns True if fields used for goal matching/dueDate computation are populated, else False"""
        if not self.birthDate or not self.country:
            return False
        if not self.degrees.exists():
            return False
        if not self.states.exists():
            return False
        if not self.hospitals.exists():
            return False
        if not self.specialties.exists():
            return False
        if not self.subspecialties.exists():
            for ps in self.specialties.all():
                if ps.subspecialties.exists():
                    # subspecs for specialty exist but user has not selected any
                    return False
        return True

    def measureComplete(self):
        """Returns a integer in range 0-100 for a measure of profile completeness"""
        total = 4
        filled = 0
        include_subspec = False
        # multivalue fields
        if self.degrees.exists():
            filled += 1
        if self.states.exists():
            filled += 1
        if self.hospitals.exists():
            filled += 1
        if self.specialties.exists():
            filled += 1
            for ps in self.specialties.all():
                if ps.subspecialties.exists():
                    include_subspec = True
                    break
            if include_subspec:
                total += 1
                if self.subspecialties.exists():
                    filled += 1
        # single-value fields
        keys = ('country','birthDate','npiNumber','residency_program', 'residencyEndDate')
        total += len(keys)
        for key in keys:
            if getattr(self, key): # count truthy values
                filled += 1
        # ABANumber
        if self.shouldReqABANumber():
            total += 1
            if self.ABANumber:
                filled += 1
        # ABIMNumber
        if self.shouldReqABIMNumber():
            total += 1
            if self.ABIMNumber:
                filled += 1
        return int(round(100.0*filled/total))

    def formatDegrees(self):
        return ", ".join([d.abbrev for d in self.degrees.all()])
    formatDegrees.short_description = "Primary Role"

    def formatSpecialties(self):
        return ", ".join([d.name for d in self.specialties.all()])
    formatSpecialties.short_description = "Specialties"

    def formatSubSpecialties(self):
        subspecs = self.subspecialties \
            .select_related('specialty') \
            .all() \
            .order_by('specialty','name')
        return ", ".join(["{0.specialty.name}/{0.name}".format(d) for d in subspecs])
    formatSubSpecialties.short_description = "SubSpecialties"

    def isNurse(self):
        degrees = self.degrees.all()
        return any([m.isNurse() for m in degrees])

    def isPhysician(self):
        degrees = self.degrees.all()
        return any([m.isPhysician() for m in degrees])

    def getActiveCmetags(self):
        """Need to query the through relation to filter by is_active=True"""
        return ProfileCmetag.objects.select_related('tag').filter(profile=self, is_active=True)

    def getActiveSRCmetags(self):
        """Need to query the through relation to filter by is_active=True"""
        return ProfileCmetag.objects.select_related('tag').filter(profile=self, is_active=True, tag__srcme_only=True)

    def getAuth0Id(self):
        delim = '|'
        if delim in self.socialId:
            L = self.socialId.split(delim, 1)
            return L[-1]

    def allowUserGoals(self):
        """Returns True if self.organization.activateGoals is True, else False"""

        if self.organization and self.organization.activateGoals:
            return True
        return False

    def isForTestTransaction(self):
        """Test if user.email matches TEST_CARD_EMAIL_PATTERN
        Returns:int/None code from email or None if no match
        """
        user_email = self.user.email
        m = TEST_CARD_EMAIL_PATTERN.match(user_email)
        if m:
            return int(m.groups()[0])
        return None

    def initializeFromPlanKey(self, plan_key):
        """Used by auth_backends to assign self.degrees, specialties, tags based on plan
        Note: this is used for non-Enterprise customers
        Args:
            plan_key: SubscriptionPlanKey instance
        """
        from .subscription import SubscriptionPlan
        self.degrees.add(plan_key.degree)
        if plan_key.specialty:
            ps = plan_key.specialty
            self.specialties.add(ps)
            specTags = ps.cmeTags.all()
            for t in specTags:
                pct = ProfileCmetag.objects.create(tag=t, profile=self, is_active=True)
            # check if can add SA-CME tag
            if self.isPhysician() and ps.name in SACME_SPECIALTIES:
                satag = CmeTag.objects.get(name=CmeTag.SACME)
                pct = ProfileCmetag.objects.create(tag=satag, profile=self, is_active=True)
        # 2019-05-26: add any default tags set by plan
        plan = SubscriptionPlan.objects.get(planId=self.planId)
        for t in plan.tags.all():
            if not ProfileCmetag.objects.filter(tag=t, profile=self).exists():
                pct = ProfileCmetag.objects.create(tag=t, profile=self, is_active=True)
                logger.info('Add {0} tag from plan for userid {0.profile.pk}'.format(pct))

    def getConditionalTags(self, specnames):
        """Used by self.addOrActivateTags to check if SACME or MOC tag can be added.
        Args:
            specnames: list/set of PracticeSpecialty names from profile.specialties
        Returns: set
        """
        add_tags = set([])
        if not self.isPhysician():
            return add_tags
        satag = CmeTag.objects.get(name=CmeTag.SACME)
        moctag = CmeTag.objects.get(name=CmeTag.ABIM_MOC)
        for specname in specnames:
            # Criteria for adding SA-CME tag
            if specname in SACME_SPECIALTIES:
                add_tags.add(satag)
            # Criteria for adding ABIM_MOC tag (can apply in addition to sacme)
            if specname in ABIM_MOC_SPECIALTIES and self.ABIMNumber and self.npiNumber and self.birthDate:
                add_tags.add(moctag)
        return add_tags

    def addOrActivateCmeTags(self):
        """Used to add/activate relevant cmeTags based on:
            specialties: tags whose name matches the specialty name
            subspecialties: subspec.cmeTags
            fluoroscopyStates: add FLUOROSCOPY tag
            For plans having allowProfileStateTags=true:
                states: state.cmeTags
                deaStates: state.deaTags
                state.doTags if DO degree
        Returns: set of CmeTag instances
        """
        from .subscription import UserSubscription
        deg_abbrevs = [d.abbrev for d in self.degrees.all()]
        is_do = Degree.DO in deg_abbrevs
        add_tags = set([]) # active tags
        specnames = [ps.name for ps in self.specialties.all()]
        cond_tags = self.getConditionalTags(specnames)
        for t in cond_tags:
            add_tags.add(t)

        spectags = CmeTag.objects.filter(name__in=specnames)
        for t in spectags:
            add_tags.add(t)
        for subspec in self.subspecialties.all():
            for t in subspec.cmeTags.all():
                add_tags.add(t)
        if self.fluoroscopyStates.exists():
            fluotag = CmeTag.objects.get(name=CmeTag.FLUOROSCOPY)
            add_tags.add(fluotag)
            rstag = CmeTag.objects.get(name=CmeTag.RADIATION_SAFETY)
            add_tags.add(rstag)
        # State-specific tags (including StateDEAtag, State DO tags) for specific plans only
        allowStateTags = True if self.organization else False
        if not self.organization:
            us = UserSubscription.objects.getLatestSubscription(self.user)
            if us and us.plan.allowProfileStateTags:
                allowStateTags = True
        if allowStateTags:
            hasDEA = len(self.deaStateSet) > 0
            for state in self.states.all():
                for t in state.cmeTags.all():
                    add_tags.add(t)
                # deaTags
                dcts = StateDeatag.objects.filter(state=state)
                for dct in dcts:
                    if dct.dea_in_state:
                        # user must have DEA license in this state
                        if state.pk in self.deaStateSet:
                            add_tags.add(dct.tag)
                    elif hasDEA:
                        # user has DEA license in some state
                        add_tags.add(dct.tag)
                # doTags
                if is_do:
                    for t in state.doTags.all():
                        add_tags.add(t)
        # Process add_tags: these are the active tags
        created_tags = set([]) # newly created tags
        for t in add_tags:
            # tag may exist from a previous assignment
            pct, created = ProfileCmetag.objects.get_or_create(profile=self, tag=t)
            if created:
                logger.info('New ProfileCmetag: {0}'.format(pct))
                created_tags.add(t)
            elif not pct.is_active:
                pct.is_active = True
                pct.save(update_fields=('is_active',))
                logger.info('Re-activate ProfileCmetag: {0}'.format(pct))
        return (add_tags, created_tags)

    def updateProfileForNewPlan(self, old_plan, new_plan):
        """Update profile.planId and check if need to add/deactivate
        tags based on new_plan
        Args:
            old_plan: SubscriptionPlan instance
            new_plan: SubscriptionPlan instance
        """
        self.planId = new_plan.planId
        self.save(update_fields=('planId',))
        # check if need to deactivate tags
        deactivated_tags = set([])
        dpcts = []
        if not new_plan.allowProfileStateTags:
            # new plan does not allow state specific tags
            for state in self.states.all():
                for t in state.cmeTags.all():
                    if ProfileCmetag.objects.filter(tag=t, profile=self).exists():
                        dpcts.append(ProfileCmetag.objects.get(tag=t, profile=self))
                for t in state.doTags.all():
                    if ProfileCmetag.objects.filter(tag=t, profile=self).exists():
                        dpcts.append(ProfileCmetag.objects.get(tag=t, profile=self))
                dcts = StateDeatag.objects.filter(state=state)
                for dct in dcts:
                    t = dct.tag
                    if ProfileCmetag.objects.filter(tag=t, profile=self).exists():
                        dpcts.append(ProfileCmetag.objects.get(tag=t, profile=self))
        # process deactivated_tags
        for pct in dpcts:
            pct.is_active = False
            pct.save()
            deactivated_tags.add(pct.tag)
            logger.info('updateProfileForNewPlan: deactivate tag {0.tag} for userid {0.profile.pk}'.format(pct))
        # add any default plantags from new_plan
        for t in new_plan.tags.all():
            if not ProfileCmetag.objects.filter(tag=t, profile=self).exists():
                pct = ProfileCmetag.objects.create(tag=t, profile=self, is_active=True)
                logger.info('Add {0} plantag for userid {0.profile.pk}'.format(pct))
        add_tags, created_tags = self.addOrActivateCmeTags()
        return (add_tags, deactivated_tags)

    @cached_property
    def activeCmeTagSet(self):
        """All active pcts. Used in goal matching calculations
        getActiveCmetags returns pct qset. Return tag pks from it.
        """
        return set([m.tag.pk for m in self.getActiveCmetags()])

    @cached_property
    def activeSRCmeTagSet(self):
        """Active srcme_only pcts. Used in goal matching calculations"""
        return set([m.tag.pk for m in self.getActiveSRCmetags()])

    @cached_property
    def degreeSet(self):
        """Used in goal matching calculations"""
        return set([m.pk for m in self.degrees.all()])

    @cached_property
    def specialtySet(self):
        """Used in goal matching calculations"""
        return set([m.pk for m in self.specialties.all()])

    @cached_property
    def subspecialtySet(self):
        """Used in goal matching calculations"""
        return set([m.pk for m in self.subspecialties.all()])

    @cached_property
    def stateSet(self):
        """Used in goal matching calculations"""
        return set([m.pk for m in self.states.all()])

    @cached_property
    def deaStateSet(self):
        """Used in goal matching calculations"""
        return set([m.pk for m in self.deaStates.all()])

    @cached_property
    def fluoroscopyStateSet(self):
        """Used in goal matching calculations"""
        return set([m.pk for m in self.fluoroscopyStates.all()])

    @cached_property
    def hospitalSet(self):
        """Used in goal matching calculations"""
        return set([m.pk for m in self.hospitals.all()])


# Many-to-many through relation between Profile and CmeTag
class ProfileCmetag(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, db_index=True)
    tag = models.ForeignKey(CmeTag, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('profile','tag')
        ordering = ['tag',]

    def __str__(self):
        return '{0.tag}|{0.is_active}'.format(self)



class EligibleSiteManager(models.Manager):
    def getSiteIdsForProfile(self, profile):
        """Returns list of EligibleSite ids whose specialties intersect
        with the profile's specialties
        """
        specids = [s.pk for s in profile.specialties.all()]
        # need distinct here to weed out dups
        esiteids = EligibleSite.objects.filter(specialties__in=specids).values_list('id', flat=True).distinct()
        return esiteids

@python_2_unicode_compatible
class EligibleSite(models.Model):
    """Eligible (or white-listed) sites that will be recognized by the plugin. An eligible site can be: a wiki, a single journal, or an aggregator site such as ScienceDirect.
    """
    SITE_TYPE_JOURNAL = 1
    SITE_TYPE_WIKI = 2
    SITE_TYPE_DATABASE = 3
    # fields
    site_type = models.PositiveIntegerField(default=1,
        choices=(
            (SITE_TYPE_JOURNAL, 'Journal'),
            (SITE_TYPE_WIKI, 'Wiki'),
            (SITE_TYPE_DATABASE, 'Database')
        ),
        help_text='Example: radiopaedia.org is a wiki. JAMA is a journal'
    )
    domain_name = models.CharField(max_length=100,
        help_text='A proper domain name without the scheme and no slashes. Example: jamanetwork.com')
    domain_title = models.CharField(max_length=300,
        help_text='e.g. Journal of Nuclear Medicine')
    journal_home_page = models.CharField(max_length=200, blank=True, default='',
        help_text='Journal homepage if different from domain_name. e.g. jamanetwork.com/journals/jamacardiology/ This allows the plugin to recognize the home page even though it itself is not a whitelisted article.')
    citation_journal_title = models.CharField(max_length=200, blank=True, default='',
        help_text='If this is a journal site, specify its citation_journal_title so that search results can be matched to this EligibleSite'
    )
    preferred_title_key = models.CharField(max_length=40, blank=True, default='',
        help_text='The title key name to use when extracting title from google search results. If not specified, will use title.'
    )
    example_url = models.URLField(max_length=1000,
        help_text='A URL within the given domain')
    example_title = models.CharField(max_length=300, blank=True,
        help_text='Label for the example URL')
    verify_journal = models.BooleanField(default=False,
            help_text='If True, need to verify article belongs to an allowed journal before making offer. Used for ScienceDirect and similar sites.')
    issn = models.CharField(max_length=9, blank=True, default='', help_text='ISSN')
    electronic_issn = models.CharField(max_length=9, blank=True, default='', help_text='Electronic ISSN')
    description = models.CharField(max_length=500, blank=True)
    specialties = models.ManyToManyField(PracticeSpecialty, blank=True)
    needs_ad_block = models.BooleanField(default=False)
    all_specialties = models.BooleanField(default=False)
    is_unlisted = models.BooleanField(default=False, blank=True, help_text='True if site should be unlisted')
    page_title_prefix = models.CharField(max_length=100, blank=True, default='', help_text='Common prefix in page titles will be stripped from the offer description.')
    page_title_suffix = models.CharField(max_length=100, blank=True, default='', help_text='Common suffix in page titles will be stripped from the offer description.')
    strip_title_after = models.CharField(max_length=60, blank=True, default='',
        help_text='Strip all characters from the page title after the given term. (e.g. the pipe symbol: |). Used for sites like Nature.')
    doi_prefixes = models.CharField(max_length=80, blank=True, default='',
            help_text='Comma separated list of common doi prefixes of articles of this site')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = EligibleSiteManager()

    def __str__(self):
        return self.domain_name + ' - ' + self.domain_title


def entry_document_path(instance, filename):
    return '{0}/uid_{1}/{2}'.format(settings.FEED_MEDIA_BASEDIR, instance.user.id, filename)

@python_2_unicode_compatible
class Document(models.Model):
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='documents',
        db_index=True
    )
    document = models.FileField(upload_to=entry_document_path)
    name = models.CharField(max_length=255, blank=True, help_text='Original file name')
    md5sum = models.CharField(max_length=32, blank=True, help_text='md5sum of the document file')
    content_type = models.CharField(max_length=100, blank=True, help_text='file content_type')
    image_h = models.PositiveIntegerField(null=True, blank=True, help_text='image height')
    image_w = models.PositiveIntegerField(null=True, blank=True, help_text='image width')
    is_thumb = models.BooleanField(default=False, help_text='True if the file is an image thumbnail')
    set_id = models.CharField(max_length=36, blank=True, help_text='Used to group an image and its thumbnail into a set')
    is_certificate = models.BooleanField(default=False, help_text='True if file is a certificate (if so, will be shared in audit report)')
    referenceId = models.CharField(max_length=255,
        null=True,
        blank=True,
        unique=True,
        default=None,
        help_text='alphanum unique key generated from the document id')
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.md5sum

class LicenseType(models.Model):
    TYPE_RN = 'RN'
    TYPE_DEA = 'DEA'
    TYPE_MB = 'Medical Board'
    TYPE_STATE = 'State'
    TYPE_FLUO = 'Fluoroscopy'
##    TYPE_TELEMEDICINE = 'Out-of-State-Telemedicine'
    # fields
    name = models.CharField(max_length=30, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class StateLicenseManager(models.Manager):
    def getLatestLicenseForUser(self, user, licenseTypeName):
        qset = user.statelicenses \
            .select_related('licenseType') \
            .filter(licenseType__name=licenseTypeName, is_active=True) \
            .order_by('-expireDate')
        if qset.exists():
            return qset[0]
        return None

    def getLatestSetForUser(self, user):
        """Finds the latest (by expireDate) license per (state, licenseType, licenseNumber)
        for the given user. This uses Postgres SELECT DISTINCT ON to return the
        first row of each (licenseType, state, -expireDate) subset.
        Reference: https://docs.djangoproject.com/en/1.11/ref/models/querysets/#django.db.models.query.QuerySet.distinct
        Ref: https://stackoverflow.com/questions/20582966/django-order-by-filter-with-distinct
        Returns: queryset
        """
        return StateLicense.objects.filter(user=user, is_active=True, expireDate__isnull=False) \
            .order_by('licenseType_id', 'state_id', 'licenseNumber', '-expireDate') \
            .distinct('licenseType','state', 'licenseNumber')

    def getLatestSetForUserLtypeState(self, user, ltype, state):
        """Finds the latest (by expireDate) license per licenseNumber for the given user, state, and licenseType.
        For most users this returns 0 or 1 license. Some users have multiple distinct licenses for the same (ltype, state).
        Returns: queryset
        """
        fkw = dict(licenseType=ltype,
                state=state,
                is_active=True,
                expireDate__isnull=False)
        qs = user.statelicenses.filter(**fkw) \
            .order_by('licenseNumber','-expireDate') \
            .distinct('licenseNumber')
        return qs

    def partitionByStatusForUser(self, user):
        """Get the latest set of licenses for the given user, and partition them
        into 3 status groups: EXPIRED, EXPIRING, COMPLETED.
        This method is used by email_service_provider module.
        Args:
            user: User instance
        Returns: dict {
            EXPIRED: list of StateLicenses
            EXPIRING: ,,
            COMPLETED: ,,
        }
        """
        now = timezone.now()
        expiringCutoffDate = now + timedelta(days=self.model.EXPIRING_CUTOFF_DAYS)
        statelicenses = self.getLatestSetForUser(user)
        expired = []; expiring = []; completed = []
        for sl in statelicenses:
            if not sl.expireDate or sl.expireDate < now:
                expired.append(sl)
            elif sl.expireDate <= expiringCutoffDate:
                expiring.append(sl)
            else:
                completed.append(sl)
        data = {
                self.model.EXPIRED: expired,
                self.model.EXPIRING: expiring,
                self.model.COMPLETED: completed
            }
        return data

    def determineSubCatg(self, licenseType, state, licenseNumber):
        """Determine subcatg of license"""
        if licenseType.name == LicenseType.TYPE_STATE:
            if state.abbrev == 'TX' and licenseNumber.startswith('TM'):
                return StateLicense.SUB_CATG_TM
        return StateLicense.SUB_CATG_DEFAULT

class StateLicense(models.Model):
    EXPIRING_CUTOFF_DAYS = 90 # expireDate cutoff for expiring goals (match UserGoal const)
    MIN_INTERVAL_DAYS = 365 # mininum license interval for renewal
    EXPIRED = 'EXPIRED'
    EXPIRING = 'EXPIRING'
    COMPLETED = 'COMPLETED'
    SUB_CATG_DEFAULT = 0
    SUB_CATG_TM = 1
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='statelicenses',
        db_index=True
    )
    state = models.ForeignKey(State,
        on_delete=models.CASCADE,
        related_name='statelicenses',
        db_index=True
    )
    licenseType = models.ForeignKey(LicenseType,
        on_delete=models.CASCADE,
        related_name='statelicenses',
        db_index=True
    )
    subcatg = models.IntegerField(
        default=0,
        blank=True,
        choices=((SUB_CATG_DEFAULT, 'Default'), (SUB_CATG_TM, 'Telemedicine')),
        help_text='Sub-category for State licenses.'
    )
    licenseNumber = models.CharField(max_length=40, blank=True, default='',
            help_text='License number')
    expireDate = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True,
            help_text='Set to false when license is inactivated')
    removeDate = models.DateTimeField(null=True, blank=True,
            help_text='Set when license is in-activated')
    modifiedBy = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='modstatelicenses',
        blank=True,
        null=True,
        db_index=True,
        help_text='User who created or last modified this row'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = StateLicenseManager()

    class Meta:
        unique_together = ('user','state','licenseType','subcatg', 'expireDate', 'is_active')

    def __str__(self):
        if self.expireDate:
            return "{0.pk}|{0.licenseType}|{0.state}|{0.subcatg}|{0.expireDate:%Y-%m-%d}".format(self)
        return "{0.pk}|{0.licenseType}|{0.state}|{0.subcatg}|expireDate unset".format(self)

    def isUnInitialized(self):
        return self.licenseNumber == '' or not self.expireDate

    def getLabelForCertificate(self):
        """Returns str e.g. California RN License #12345
        """
        label = "{0.state.name} {0.licenseType.name} License #{0.licenseNumber}".format(self)
        return label

    @property
    def displayLabel(self):
        """Returns str e.g. California RN License #12345 expiring yyyy-mm-dd
        """
        if self.expireDate:
            label = "{0.state.name} {0.licenseType.name} License #{0.licenseNumber} expiring {0.expireDate:%Y-%m-%d}".format(self)
        else:
            label = "{0.state.name} {0.licenseType.name} License #{0.licenseNumber}".format(self)
        return label

    def inactivate(self, removeDate, modifiedBy):
        self.is_active = False
        self.removeDate = removeDate
        self.modifiedBy = modifiedBy
        self.save()

    def checkExpireDateForRenewal(self, expireDate):
        """Returns True if expireDate is more than cutoff days from self.expireDate
        else return False
        """
        if self.expireDate and expireDate > self.expireDate:
            tdiff = expireDate - self.expireDate
            if tdiff.days >= StateLicense.MIN_INTERVAL_DAYS:
                return True
        return False

    def isDateMatch(self, dt):
        """Args:
            dt: datetime object
        Returns: bool True if self.expireDate.date == dt.date
        """
        if not self.expireDate:
            return False
        return self.expireDate.date() == dt.date()

#
# UI Tab specification
#
class UITabManager(models.Manager):
    def getTabsByTitles(self, titles):
        """Args:
            titles: list of tab titles
        Returns: dict: {title => UITab instance}
        """
        data = {}
        qs = self.model.objects.filter(title__in=titles)
        for m in qs:
            data[m.title] = m
        return data

class UITab(models.Model):
    title = models.CharField(max_length=30, unique=True, help_text='Tab title')
    icon_1x = models.CharField(max_length=500, blank=True, default='', help_text='Tab icon 1x relative path')
    icon_2x = models.CharField(max_length=500, blank=True, default='', help_text='Tab icon 2x relative path')
    icon_3x = models.CharField(max_length=500, blank=True, default='', help_text='Tab icon 3x relative path')
    contents = JSONField(default=dict, blank=True, help_text='JSON object that represents the contents of the tab. See existing tabs as a guide.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = UITabManager()

    def __str__(self):
        return self.title

    def toUIDict(self, index):
        """Return dict structure as expected by UI"""
        return {
            'index': index,
            'title': self.title,
            'icon': {
                "at1x": self.icon_1x,
                "at2x": self.icon_2x,
                "at3x": self.icon_3x,
            },
            'contents': self.contents.copy() 
        }
