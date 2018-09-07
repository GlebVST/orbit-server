from __future__ import unicode_literals
import logging
from datetime import datetime, timedelta
from hashids import Hashids
import pytz
import re
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from django.contrib.postgres.search import SearchVector
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible

logger = logging.getLogger('gen.models')

#
# constants (should match the database values)
#
CMETAG_SACME = 'SAM/SA-CME'
# specialties that have SA-CME tag pre-selected on OrbitCmeOffer
SACME_SPECIALTIES = (
    'Radiology',
    'Radiation Oncology',
    'Pathology',
)
TEST_CARD_EMAIL_PATTERN = re.compile(r'testcode-(?P<code>\d+)')
HASHIDS_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890!@' # extend alphabet with ! and @

ACTIVE_OFFDATE = datetime(3000,1,1,tzinfo=pytz.utc)

# Q objects
Q_ADMIN = Q(username__in=('admin','radmin')) # django admin users not in auth0
Q_IMPERSONATOR = Q(is_staff=True) & ~Q_ADMIN

def default_expire():
    """1 hour from now"""
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


# CME tag types (SA-CME tag has priority=1)
class CmeTagManager(models.Manager):
    def getSpecTags(self):
        pspecs = PracticeSpecialty.objects.all()
        pnames = [p.name for p in pspecs]
        tags = self.model.objects.filter(name__in=pnames)
        return tags

@python_2_unicode_compatible
class CmeTag(models.Model):
    name= models.CharField(max_length=40, unique=True)
    priority = models.IntegerField(
        default=0,
        help_text='Used for non-alphabetical sort.'
    )
    description = models.CharField(max_length=200, unique=True, help_text='Long-form name')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = CmeTagManager()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = 'CME Tags'
        ordering = ['-priority', 'name']


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



class HospitalManager(models.Manager):

    def find_st_group(self, name):
        uname = name.upper()
        if uname.endswith("'S"):
            uname.strip("'S")
        if uname in self.model.ST_GROUPS:
            return uname
        if uname.endswith('S'):
            uname = uname[0:-1]
            if uname in self.model.ST_GROUPS:
                return uname
        return None

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
        qset = None
        L = search_term.split(); f = L[0].upper(); num_tokens = len(L)
        if (num_tokens > 1) and (f == 'ST' or f == 'ST.'):
            key = self.find_st_group(L[1])
            if key:
                name_list = self.model.ST_GROUPS[key]
                if num_tokens > 2:
                    rest = ' ' + u' '.join(L[2:])
                else:
                    rest = ''
                Q_list = [Q(search=name+rest) for name in name_list]
                Q_combined = reduce(lambda x,y: x|y, Q_list)
                qset = qs_all.filter(Q_combined)
        if not qset:
            qset = qs_all.filter(search=search_term)
        return qset.order_by('name','city')

class ResidencyProgramManager(models.Manager):
    def get_queryset(self):
        return super(ResidencyProgramManager, self).get_queryset().filter(hasResidencyProgram=True)

    def search_filter(self, search_term):
        base_qs = self.model.residency_objects.all()
        return self.model.objects.search_filter(search_term, base_qs)

@python_2_unicode_compatible
class Hospital(models.Model):
    ST_GROUPS = {
        u'AGNES': (u'ST AGNES', u'ST. AGNES'),
        u'ALEXIUS': (u'ST ALEXIUS', u'ST. ALEXIUS'),
        u'ANTHONY': (u'ST ANTHONY', u"ST. ANTHONY'S", u"ST ANTHONY'S", u'ST. ANTHONY', u'ST ANTHONYS'),
        u'BERNARD': (u'ST. BERNARD', u'ST. BERNARDINE', u'ST BERNARD', u'ST. BERNARDS'),
        u'CATHERINE': (u'ST CATHERINE', u"ST CATHERINE'S", u'ST. CATHERINE'),
        u'CHARLES': (u'ST CHARLES', u'ST. CHARLES'),
        u'CLAIR': (u'ST CLAIR', u'ST. CLAIRE'),
        u'CLARE': (u'ST. CLARE', u'ST CLARES'),
        u'CLOUD': (u'ST CLOUD', u'ST. CLOUD'),
        u'DAVID': (u"ST. DAVID'S", u'ST DAVIDS', u"ST DAVID'S"),
        u'ELIZABETH': (u'ST. ELIZABETH', u"ST. ELIZABETH'S", u'ST ELIZABETH', u'ST ELIZABETHS'),
        u'FRANCIS': (u'ST. FRANCIS', u'ST FRANCIS'),
        u'JAMES': (u'ST JAMES', u'ST. JAMES'),
        u'JOHN': (u'ST. JOHN', u'ST JOHN', u"ST. JOHN'S", u"ST JOHN'S", u'ST JOHNS'),
        u'JOSEPH': (u"ST. JOSEPH'S", u"ST JOSEPH'S", u'ST JOSEPH', u'ST. JOSEPH', u'ST JOSEPHS'),
        u'LOUIS': (u'ST. LOUIS', u'ST. LOUISE'),
        u'LUKE': (u'ST. LUKE', u"ST. LUKES'S", u'ST LUKE', u"ST LUKE'S", u'ST LUKES', u"ST. LUKE'S", u'ST. LUKES'),
        u'MARK': (u"ST. MARK'S", u'ST. MARKS'),
        u'MARY': (u'ST MARYS', u"ST MARY'S", u'ST MARY', u'ST. MARY', u"ST. MARY'S"),
        u'PETER': (u'ST PETERSBURG', u'ST PETERS', u"ST. PETER'S"),
        u'VINCENT': (u'ST VINCENT', u"ST. VINCENT'S", u"ST VINCENT'S", u'ST. VINCENT'),
    }
    state = models.ForeignKey(State,
        on_delete=models.CASCADE,
        related_name='hospitals',
        db_index=True
    )
    name = models.CharField(max_length=120, db_index=True)
    display_name = models.CharField(max_length=200, help_text='Used for display')
    city = models.CharField(max_length=80, db_index=True)
    website = models.URLField(max_length=500, blank=True)
    county = models.CharField(max_length=60, blank=True)
    hasResidencyProgram = models.BooleanField(default=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = HospitalManager() # default manager
    residency_objects = ResidencyProgramManager()

    def __str__(self):
        return self.display_name

    def str_long(self):
        return "{0.pk}|{0.display_name}|{0.city}|{0.state.abbrev}".format(self)

    class Meta:
        ordering = ['name',]
        unique_together = ('state','city','name')


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
        return self.name

    def formatTags(self):
        return ", ".join([t.name for t in self.cmeTags.all()])
    formatTags.short_description = "cmeTags"

    class Meta:
        verbose_name_plural = 'Practice Sub Specialties'
        unique_together = ('specialty', 'name')
        ordering = ['name',]


@python_2_unicode_compatible
class Organization(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True, help_text='Org code for display')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    credits = models.FloatField(default=0,
            help_text='Computed total credits earned by this org since creditStartDate until today.')
    creditStartDate = models.DateTimeField(null=True, blank=True,
            help_text='Start date of total credits calculation')
    creditEndDate = models.DateTimeField(null=True, blank=True,
            help_text='End date of total credits calculation')
    providerStat = JSONField(default='', blank=True)

    def __str__(self):
        return self.code


class OrgFileManager(models.Manager):

    def getCsvFileDialect(self, orgfile):
        """This is called the OrgFileUpload hander to check the file dialect
        Args:
            orgfile: OrgFile instance
        Expected file format: lastName, firstName, email, role
        Returns: str - dialect found. None if none found
        """
        import csv
        with open(orgfile.document, 'rb') as f:
            try:
                dialect = csv.Sniffer().sniff(f.read(1024))
            except csv.Error:
                logger.error('getCsvFileDialect csv.Error for file_id {0.pk}'.format(orgfile))
                return None
            else:
                return dialect

def orgfile_document_path(instance, filename):
    return '{0}/org_{1}/{2}'.format(settings.ORG_MEDIA_BASEDIR, instance.organization.id, filename)

@python_2_unicode_compatible
class OrgFile(models.Model):
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='orgfiles',
        db_index=True
    )
    organization = models.ForeignKey(Organization,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='orgfiles'
    )
    document = models.FileField(upload_to=orgfile_document_path,
        help_text='Original document uploaded by user')
    csvfile = models.FileField(null=True, blank=True, upload_to=orgfile_document_path,
            help_text='If original document is not in plain-text CSV, then upload converted file here')
    name = models.CharField(max_length=255, blank=True, help_text='document file name')
    content_type = models.CharField(max_length=100, blank=True, help_text='document content_type')
    processed = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    objects = OrgFileManager()

    class Meta:
        verbose_name_plural = 'Enterprise File Uploads'

    def __str__(self):
        return self.name


class OrgMemberManager(models.Manager):

    def makeFullName(self, firstName, lastName):
        return u"{0} {1}".format(firstName.upper(), lastName.upper())

    def createMember(self, org, profile, is_admin=False):
        """
        Check if user instance aleady exists for the given email
            - raise ValueError (to respect existing user account)
        Args:
            org: Organization instance
            profile: Profile instance
            is_admin: bool default is False
        Returns: OrgAdmin model instance
        """
        user = profile.user
        fullName = self.makeFullName(profile.firstName, profile.lastName)
        compliance = 4 if is_admin else 2
        m = self.model.objects.create(
                organization=org,
                user=user,
                fullname=fullName,
                compliance=compliance,
                is_admin=is_admin)
        return m

    def search_filter(self, search_term, filter_kwargs, orderByFields):
        """Returns a queryset that filters active OrgMembers by the given org and search_term
        Args:
            search_term: str : to query fullname and username
            filter_kwargs: dict must contain key: organization, else raise KeyError
            orderByFields: tuple of fields to order by
        Returns: queryset of active OrgMembers
        """
        org =  filter_kwargs['organization'] # ensure org is contained to filter by a given organization
        base_qs = self.model.objects.select_related('user', 'user__profile').filter(**filter_kwargs)
        qs1 = base_qs.filter(fullname__contains=search_term.upper())
        qs2 = base_qs.filter(user__username__istartswith=search_term)
        qs = qs1
        if not qs.exists():
            qs = qs2
        return qs.order_by(*orderByFields)


@python_2_unicode_compatible
class OrgMember(models.Model):
    organization = models.ForeignKey(Organization,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='orgmembers'
    )
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='orgmembers',
    )
    fullname = models.CharField(max_length=100, db_index=True,
            help_text='Uppercase first and last name for search')
    is_admin = models.BooleanField(default=False, db_index=True,
            help_text='True if user is an admin for this organization')
    removeDate = models.DateTimeField(null=True, blank=True,
            help_text='date the member was removed')
    compliance = models.PositiveSmallIntegerField(default=1, db_index=True,
            help_text='Cached compliance level aggregated over user goals')
    setPasswordEmailSent = models.BooleanField(default=False,
            help_text='Set to True when password-ticket email is sent')
    orgfiles = models.ManyToManyField(OrgFile, related_name='orgmembers')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = OrgMemberManager()

    class Meta:
        unique_together = ('organization', 'user')
        verbose_name_plural = 'Enterprise Members'

    def __str__(self):
        return '{0.user}/{0.organization}'.format(self)


class ProfileManager(models.Manager):

    def createUserAndProfile(self, email, planId, inviter=None, affiliateId='', socialId='', pictureUrl='', verified=False, organization=None, firstName='', lastName=''):
        """Create new User instance and new Profile instance"""
        hashgen = Hashids(salt=settings.HASHIDS_SALT, alphabet=HASHIDS_ALPHABET, min_length=5)
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
    specialties = models.ManyToManyField(PracticeSpecialty, blank=True)
    subspecialties = models.ManyToManyField(SubSpecialty, blank=True)
    states = models.ManyToManyField(State, blank=True)
    hospitals = models.ManyToManyField(Hospital, blank=True)
    verified = models.BooleanField(default=False, help_text='User has verified their email via Auth0')
    is_affiliate = models.BooleanField(default=False, help_text='True if user is an approved affiliate')
    accessedTour = models.BooleanField(default=False, help_text='User has commenced the online product tour')
    # TODO: drop these cmeStartDate/EndDate? these are goal-specific
    cmeStartDate = models.DateTimeField(null=True, blank=True, help_text='Start date for CME requirements calculation')
    cmeEndDate = models.DateTimeField(null=True, blank=True, help_text='Due date for CME requirements fulfillment')
    affiliateId = models.CharField(max_length=20, blank=True, default='', help_text='If conversion, specify Affiliate ID')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = ProfileManager()

    def __str__(self):
        return '{0.firstName} {0.lastName}'.format(self)

    def getFullName(self):
        return u"{0} {1}".format(self.firstName, self.lastName)

    def getFullNameAndDegree(self):
        degrees = self.degrees.all()
        degree_str = ", ".join(str(degree.abbrev) for degree in degrees)
        return u"{0} {1}, {2}".format(self.firstName, self.lastName, degree_str)

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
        keys = ('country','birthDate','affiliationText','interestText','npiNumber','residency', 'residencyEndDate')
        total += len(keys)
        for key in keys:
            if getattr(self, key): # count truthy values
                filled += 1
        return int(round(100.0*filled/total))

    def formatDegrees(self):
        return ", ".join([d.abbrev for d in self.degrees.all()])
    formatDegrees.short_description = "Primary Role"

    def formatSpecialties(self):
        return ", ".join([d.name for d in self.specialties.all()])
    formatSpecialties.short_description = "Specialties"

    def isNurse(self):
        degrees = self.degrees.all()
        return any([m.isNurse() for m in degrees])

    def isPhysician(self):
        degrees = self.degrees.all()
        return any([m.isPhysician() for m in degrees])

    def getActiveCmetags(self):
        """Need to query the through relation to filter by is_active=True"""
        return ProfileCmetag.objects.filter(profile=self, is_active=True)

    def getAuth0Id(self):
        delim = '|'
        if delim in self.socialId:
            L = self.socialId.split(delim, 1)
            return L[-1]

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
        self.degrees.add(plan_key.degree)
        if plan_key.specialty:
            ps = plan_key.specialty
            self.specialties.add(ps)
            specTags = ps.cmeTags.all()
            for t in specTags:
                pct = ProfileCmetag.objects.create(tag=t, profile=self, is_active=True)
            # check if can add SA-CME tag
            if self.isPhysician() and ps.name in SACME_SPECIALTIES:
                satag = CmeTag.objects.get(name=CMETAG_SACME)
                pct = ProfileCmetag.objects.create(tag=satag, profile=self, is_active=True)

    def addOrActivateCmeTags(self):
        """Used to add/activate relevant cmeTags based on:
            specialties: tags whose name matches the specialty name
            subspecialties: subspec.cmeTags
            states: state.cmeTags
        Returns: set of CmeTag instances
        """
        satag = CmeTag.objects.get(name=CMETAG_SACME)
        isPhysician = self.isPhysician()
        add_tags = set([]) # tags to be added (or re-activated if already exist)
        specnames = [ps.name for ps in self.specialties.all()]
        spectags = CmeTag.objects.filter(name__in=specnames)
        for specname in specnames:
            if isPhysician and specname in SACME_SPECIALTIES:
                add_tags.add(satag)
        for t in spectags:
            add_tags.add(t)
        for m in self.subspecialties.all():
            for t in m.cmeTags.all():
                add_tags.add(t)
        for m in self.states.all():
            for t in m.cmeTags.all():
                add_tags.add(t)
        # Process add_tags
        for t in add_tags:
            # tag may exist from a previous assignment
            pct, created = ProfileCmetag.objects.get_or_create(profile=self, tag=t)
            if created:
                logger.info('New ProfileCmetag: {0}'.format(pct))
            elif not pct.is_active:
                pct.is_active = True
                pct.save(update_fields=('is_active',))
                logger.info('Re-activate ProfileCmetag: {0}'.format(pct))
        return add_tags

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
    """Eligible (or white-listed) domains that will be recognized by the plugin.
    To start, we will have a manual system for translating data in this model
    into the AllowedUrl model.
    """
    domain_name = models.CharField(max_length=100,
        help_text='wikipedia.org')
    domain_title = models.CharField(max_length=300,
        help_text='e.g. Wikipedia Anatomy Pages')
    example_url = models.URLField(max_length=1000,
        help_text='A URL within the given domain')
    example_title = models.CharField(max_length=300, blank=True,
        help_text='Label for the example URL')
    verify_journal = models.BooleanField(default=False,
            help_text='If True, need to verify article belongs to an allowed journal before making offer.')
    issn = models.CharField(max_length=9, blank=True, default='', help_text='ISSN')
    electronic_issn = models.CharField(max_length=9, blank=True, default='', help_text='Electronic ISSN')
    description = models.CharField(max_length=500, blank=True)
    specialties = models.ManyToManyField(PracticeSpecialty, blank=True)
    needs_ad_block = models.BooleanField(default=False)
    all_specialties = models.BooleanField(default=False)
    is_unlisted = models.BooleanField(default=False, blank=True, help_text='True if site should be unlisted')
    page_title_suffix = models.CharField(max_length=60, blank=True, default='', help_text='Common suffix for page titles')
    doi_prefixes = models.CharField(max_length=80, blank=True, default='',
            help_text='Comma separated list of common doi prefixes of articles of this site')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = EligibleSiteManager()

    def __str__(self):
        return self.domain_title


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
    # fields
    name = models.CharField(max_length=30, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class StateLicenseManager(models.Manager):
    def getLatestLicenseForUser(self, user, licenseTypeName):
        qset = user.statelicenses.filter(licenseType__name=licenseTypeName).order_by('-expireDate')
        if qset.exists():
            return qset[0]
        return None

    def getLatestSetForUser(self, user):
        """Finds the latest (by expireDate) license per (state, licenseType)
        for the given user. This uses Postgres SELECT DISTINCT ON to return the
        first row of each (licenseType, state, -expireDate) subset.
        Reference: https://docs.djangoproject.com/en/1.11/ref/models/querysets/#django.db.models.query.QuerySet.distinct
        Ref: https://stackoverflow.com/questions/20582966/django-order-by-filter-with-distinct
        Returns: queryset
        """
        return StateLicense.objects.filter(user=user).order_by('licenseType_id', 'state_id', '-expireDate').distinct('licenseType','state')

class StateLicense(models.Model):
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
    licenseNumber = models.CharField(max_length=40, blank=True, default='',
            help_text='License number')
    expireDate = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = StateLicenseManager()

    class Meta:
        unique_together = ('user','state','licenseType','expireDate')

    def __str__(self):
        return self.licenseNumber

    def isUnInitialized(self):
        return self.licenseNumber == '' or not self.expireDate

    def getLabelForCertificate(self):
        """Returns str e.g. California RN License #12345
        """
        label = u"{0.state.name} {0.licenseType.name} License #{0.licenseNumber}".format(self)
        return label
