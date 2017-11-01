from __future__ import unicode_literals
import logging
import braintree
from collections import namedtuple
from datetime import datetime
from dateutil.relativedelta import *
from decimal import Decimal
import pytz
import uuid
from urlparse import urlparse
from django.conf import settings
from django.contrib.auth.models import User, Group
from django.contrib.postgres.fields import JSONField
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Prefetch, Count, Sum
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible

logger = logging.getLogger('gen.models')

from common.appconstants import (
    MAX_URL_LENGTH,
    SELF_REPORTED_AUTHORITY,
    AMA_PRA_CATEGORY_LABEL,
    PERM_VIEW_OFFER,
    PERM_VIEW_FEED,
    PERM_VIEW_DASH,
    PERM_POST_BRCME,
    PERM_POST_SRCME,
    PERM_PRINT_AUDIT_REPORT,
    PERM_PRINT_BRCME_CERT
)
#
# constants (should match the database values)
#
ENTRYTYPE_BRCME = 'browser-cme'
ENTRYTYPE_SRCME = 'sr-cme'
ENTRYTYPE_NOTIFICATION = 'notification'
CMETAG_SACME = 'SA-CME'
COUNTRY_USA = 'USA'
DEGREE_MD = 'MD'
DEGREE_DO = 'DO'
SPONSOR_BRCME = 'TUSM'
ACTIVE_OFFDATE = datetime(3000,1,1,tzinfo=pytz.utc)
INVITEE_DISCOUNT_TYPE = 'invitee'
INVITER_DISCOUNT_TYPE = 'inviter'

# maximum number of invites for which a discount is applied to the inviter's subscription.
INVITER_MAX_NUM_DISCOUNT = 10

LOCAL_TZ = pytz.timezone(settings.LOCAL_TIME_ZONE)

def makeAwareDatetime(a_date, tzinfo=pytz.utc):
    """Convert <date> to <datetime> with timezone info"""
    return timezone.make_aware(
        datetime.combine(a_date, datetime.min.time()), tzinfo)

def asLocalTz(dt):
    """Args:
        dt: aware datetime object
    Returns dt in the LOCAL_TIME_ZONE
    """
    return dt.astimezone(LOCAL_TZ)

@python_2_unicode_compatible
class Country(models.Model):
    """Names of countries for country of practice.
    """
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
    abbrev = models.CharField(max_length=5, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['country','name']
        unique_together = (('country', 'name'), ('country', 'abbrev'))

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
    """Names and abbreviations of professional degrees"""
    abbrev = models.CharField(max_length=7, unique=True)
    name = models.CharField(max_length=40)
    sort_order = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = DegreeManager()

    def __str__(self):
        return self.abbrev

    def isVerifiedForCme(self):
        """Is degree verified for CME
        Returns True if degree is MD/DO
        """
        abbrev = self.abbrev
        return abbrev == DEGREE_MD or abbrev == DEGREE_DO

    class Meta:
        ordering = ['sort_order',]

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
    description = models.CharField(max_length=200, blank=True, help_text='Used for tooltip')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = CmeTagManager()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = 'CME Tags'
        ordering = ['-priority', 'name']


@python_2_unicode_compatible
class PracticeSpecialty(models.Model):
    """Names of practice specialties.
    """
    name = models.CharField(max_length=100, unique=True)
    parent = models.ForeignKey('self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        db_index=True,
        help_text='If this entry is a sub-specialty, then specify its GeneralCert parent.'
    )
    cmeTags = models.ManyToManyField(CmeTag,
        blank=True,
        related_name='specialties',
        help_text='Eligible cmeTags for this specialty'
    )
    is_abms_board = models.BooleanField(default=False, help_text='True if this is an ABMS Board/General Cert')
    is_primary = models.BooleanField(default=False, help_text='True if this is a Primary Specialty Certificate')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def formatTags(self):
        return ", ".join([t.name for t in self.cmeTags.all()])
    formatTags.short_description = "cmeTags"

    class Meta:
        verbose_name_plural = 'Practice Specialties'


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
    jobTitle = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True, help_text='About me')
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
    socialId = models.CharField(max_length=64, blank=True, help_text='Auth0 ID')
    pictureUrl = models.URLField(max_length=1000, blank=True, help_text='Auth0 avatar URL')
    oldcmeTags = models.ManyToManyField(CmeTag, blank=True)
    cmeTags = models.ManyToManyField(CmeTag,
            through='ProfileCmetag',
            blank=True,
            related_name='profiles')
    degrees = models.ManyToManyField(Degree, blank=True) # called primaryrole in UI
    specialties = models.ManyToManyField(PracticeSpecialty, blank=True)
    verified = models.BooleanField(default=False, help_text='User has verified their email via Auth0')
    is_affiliate = models.BooleanField(default=False, help_text='True if user is an approved affiliate')
    accessedTour = models.BooleanField(default=False, help_text='User has commenced the online product tour')
    cmeDuedate = models.DateTimeField(null=True, blank=True, help_text='Due date for CME requirements fulfillment')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '{0.firstName} {0.lastName}'.format(self)

    def shouldReqNPINumber(self):
        """
        If (country=COUNTRY_USA) and (MD or DO in self.degrees),
        then npiNumber should be requested
        """
        if self.country is None:
            return False
        us = Country.objects.get(code=COUNTRY_USA)
        if self.country.pk != us.pk:
            return False
        deg_abbrevs = [d.abbrev for d in self.degrees.all()]
        has_md = DEGREE_MD in deg_abbrevs
        if has_md:
            return True
        has_do = DEGREE_DO in deg_abbrevs
        if has_do:
            return True
        return False

    def isNPIComplete(self):
        """
        True: obj.shouldReqNPINumber is False
        True: If obj.shouldReqNPINumber and npiNumber is non-blank.
        False: If obj.shouldReqNPINumber and npiNumber is blank.
        """
        if self.shouldReqNPINumber():
            if self.npiNumber:
                return True
            return False
        return True


    def isSignupComplete(self):
        """Signup is complete if the following fields are populated
            1. Country is provided
            2. One or more PracticeSpecialty
            3. One or more Degree (now called primaryRole in UI, and only 1 selection is currently allowed)
            4. user has saved a UserSubscription
        """
        if not self.country:
            return False
        if not self.specialties.exists():
            return False
        if not self.degrees.exists():
            return False
        if not self.user.subscriptions.exists():
            return False
        return True

    def getFullName(self):
        return u"{0} {1}".format(self.firstName, self.lastName)

    def getFullNameAndDegree(self):
        degrees = self.degrees.all()
        degree_str = ", ".join(str(degree.abbrev) for degree in degrees)
        return u"{0} {1}, {2}".format(self.firstName, self.lastName, degree_str)

    def formatDegrees(self):
        return ", ".join([d.abbrev for d in self.degrees.all()])
    formatDegrees.short_description = "Primary Role"

    def getActiveCmetags(self):
        """Need to query the through relation to filter by is_active=True"""
        return ProfileCmetag.filter(profile=self, is_active=True)

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


class Affiliate(models.Model):
    user = models.OneToOneField(User,
        on_delete=models.CASCADE,
        primary_key=True
    )
    affiliateId = models.CharField(max_length=20, unique=True, help_text='Affiliate ID')
    discountLabel = models.CharField(max_length=60, blank=True, default='', help_text='identifying label used in discount display')
    paymentEmail = models.EmailField(help_text='Valid email address to be used for Payouts.')
    active = models.BooleanField(default=True)
    bonus = models.DecimalField(max_digits=3, decimal_places=2, default=0.15, help_text='Fractional multipler on fully discounted priced paid by convertee')
    personalText = models.TextField(blank=True, default='', help_text='Custom personal text for display')
    photoUrl = models.URLField(max_length=1000, blank=True, help_text='Link to photo')
    jobDescription = models.TextField(blank=True)
    og_title = models.TextField(blank=True, default='Orbit', help_text='Value for og:title metatag')
    og_description = models.TextField(blank=True, default='', help_text='Value for og:description metatag')
    og_image = models.URLField(max_length=1000, blank=True, help_text='URL for og:image metatag')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '{0.affiliateId}|{0.paymentEmail}'.format(self)

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
    license_no = models.CharField(max_length=40, blank=True,
            help_text='License number')
    expiryDate = models.DateTimeField(null=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.license_no


class CustomerManager(models.Manager):
    def findBtCustomer(self, customer):
        """customer: Customer instance from db
        Returns: Braintree Customer object
        Can raise braintree.exceptions.not_found_error.NotFoundError
        """
        return braintree.Customer.find(str(customer.customerId))

    def getPaymentMethods(self, customer):
        """Get the existing payment methods (credit card only)
            customer: Customer instance from db
        Returns: [{token, number, type, expiry},]
        """
        bc = self.findBtCustomer(customer)
        results = [{
            "token": m.token,
            "number": m.masked_number,
            "type": m.card_type,
            "expiry": m.expiration_date
            } for m in bc.payment_methods]
        return results

    def addNewPaymentMethod(self, customer, payment_nonce):
        """Update bt_customer Vault: add new payment method
            customer: Customer instance from db
            payment_nonce: payment nonce prepared on client
        Returns: braintree result object from Customer.update
        Can raise braintree.exceptions.not_found_error.NotFoundError
        Reference: https://developers.braintreepayments.com/reference/request/customer/update/python#examples
        """
        result = braintree.Customer.update(str(customer.customerId), {
            "credit_card": {
                "payment_method_nonce": payment_nonce
            }
        })
        return result

    def updatePaymentMethod(self, customer, payment_nonce, token):
        """Update bt_customer Vault: add new payment method
            customer: Customer instance from db
            payment_nonce: payment nonce prepared on client
            token: existing token to update
        Returns: braintree result object from Customer.update
        Can raise braintree.exceptions.not_found_error.NotFoundError
        """
        result = braintree.Customer.update(str(customer.customerId), {
            "credit_card": {
                "payment_method_nonce": payment_nonce,
                "options": {
                    "update_existing_token": token
                }
            }
        })
        return result

    def makeSureNoMultipleMethods(self, customer):
        """
        A method to be called only when no active subscription for the customer
        so it's safe to remove all payment methods
        (note might not be used in production but in dev some users could have multiple methods).
        """
        bc = self.findBtCustomer(customer)
        # Fetch existing list of tokens
        tokens = [m.token for m in bc.payment_methods]
        num_tokens = len(tokens)
        if num_tokens > 1:
            # Cleanup all previous tokens
            for token in tokens:
                braintree.PaymentMethod.delete(token)

    def addOrUpdatePaymentMethod(self, customer, payment_nonce):
        """
        If customer has no existing tokens: add new payment method
        else if customer has 1 token: update payment method
        else if customer has >1 tokens: raise ValueError
            customer: Customer instance from db
            payment_nonce: payment nonce prepared on client
        Can raise braintree.exceptions.not_found_error.NotFoundError
        Returns: braintree result object from Customer.update
        """
        bc = self.findBtCustomer(customer)
        # Fetch existing list of tokens
        tokens = [m.token for m in bc.payment_methods]
        num_tokens = len(tokens)
        result = None
        if not num_tokens:
            # Add new payment method
            result = self.addNewPaymentMethod(customer, payment_nonce)
        elif num_tokens == 1:
            # Update existing token with the nonce
            result = self.updatePaymentMethod(customer, payment_nonce, tokens[0])
        else:
            raise ValueError('Customer has multiple payment tokens.')
        return result

    def getDateFromExpiry(self, expiry):
        """Given expiry string mm/yyyy from payment method,
        construct and return a datetime object for the end
        of that month. It assumes the card expires at the
        end of the month.
        """
        expiry_mm, expiry_yyyy = expiry.split('/')
        start_dt = datetime(int(expiry_yyyy), int(expiry_mm), 1, tzinfo=pytz.utc)
        # last day of the month, 23:59:59 utc
        end_dt = start_dt + relativedelta(day=1, months=+1, seconds=-1)
        return endt_dt

@python_2_unicode_compatible
class Customer(models.Model):
    user = models.OneToOneField(User,
        on_delete=models.CASCADE,
        primary_key=True
    )
    customerId = models.UUIDField(unique=True, editable=False, default=uuid.uuid4,
        help_text='Used for BT customerId')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = CustomerManager()

    def __str__(self):
        return str(self.customerId)

# Sponsors for entries in feed
@python_2_unicode_compatible
class Sponsor(models.Model):
    abbrev = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=200, unique=True)
    url = models.URLField(max_length=1000, blank=True, help_text='Link to website of sponsor')
    logo_url = models.URLField(max_length=1000, help_text='Link to logo of sponsor')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


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
    is_valid_expurl = models.BooleanField(default=True, help_text='Is example_url a valid URL')
    description = models.CharField(max_length=500, blank=True)
    specialties = models.ManyToManyField(PracticeSpecialty, blank=True)
    needs_ad_block = models.BooleanField(default=False)
    all_specialties = models.BooleanField(default=False)
    is_unlisted = models.BooleanField(default=False, blank=True, help_text='True if site should be unlisted')
    page_title_suffix = models.CharField(max_length=60, blank=True, default='', help_text='Common suffix for page titles')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = EligibleSiteManager()

    def __str__(self):
        return self.domain_title


# Browser CME offer
# An offer for a user is generated based on the user's plugin activity.
@python_2_unicode_compatible
class BrowserCmeOffer(models.Model):
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='offers',
        db_index=True
    )
    sponsor = models.ForeignKey(Sponsor,
        on_delete=models.PROTECT,
        related_name='offers',
        db_index=True
    )
    eligible_site = models.ForeignKey(EligibleSite,
        on_delete=models.CASCADE,
        related_name='offers',
        db_index=True)
    activityDate = models.DateTimeField()
    url = models.URLField(max_length=500, db_index=True)
    pageTitle = models.TextField(blank=True)
    suggestedDescr = models.TextField(blank=True, default='')
    expireDate = models.DateTimeField()
    redeemed = models.BooleanField(default=False)
    valid = models.BooleanField(default=True)
    credits = models.DecimalField(max_digits=5, decimal_places=2,
        help_text='CME credits to be awarded upon redemption')
    cmeTags = models.ManyToManyField(
        CmeTag,
        blank=True,
        related_name='brcmeoffers',
        through='OfferCmeTag',
        help_text='Suggested tags (intersected with user cmeTags by UI)'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.url

    def activityDateLocalTz(self):
        return self.activityDate.astimezone(LOCAL_TZ)

    def formatSuggestedTags(self):
        return ", ".join([t.name for t in self.cmeTags.all()])
    formatSuggestedTags.short_description = "suggestedTags"

    class Meta:
        verbose_name_plural = 'BrowserCME Offers'
        # list of (codename, human_readable_permission_name)
        permissions = (
            (PERM_VIEW_OFFER, 'Can view BrowserCmeOffer'),
        )

# BrowserCmeOffer-CmeTag association
@python_2_unicode_compatible
class OfferCmeTag(models.Model):
    offer = models.ForeignKey(BrowserCmeOffer, on_delete=models.CASCADE)
    tag = models.ForeignKey(CmeTag, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return '{0.tag.name}'.format(self)

    class Meta:
        unique_together = ('offer','tag')

# Extensible list of entry types that can appear in a user's feed
@python_2_unicode_compatible
class EntryType(models.Model):
    name = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=100, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


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


# Base class for all feed entries (contains fields common to all entry types)
# A entry belongs to a user, and is defined by an activityDate and a description.

AuditReportResult = namedtuple('AuditReportResult',
    'saEntries brcmeEntries otherSrCmeEntries saCmeTotal otherCmeTotal creditSumByTag'
)

class EntryManager(models.Manager):

    def prepareDataForAuditReport(self, user, startDate, endDate):
        """
        Filter entries by user and activityDate range, and order by activityDate desc.
        Partition the qset into:
            saEntries: entries with tag=CMETAG_SACME
            The non SA-CME entries are further partitioned into:
            brcmeEntries: entries with entryType=ENTRYTYPE_BRCME
            otherSrCmeEntries: non SA-CME entries (sr-cme only)
        Returns AuditReportResult
        """
        satag = CmeTag.objects.get(name=CMETAG_SACME)
        filter_kwargs = dict(
            user=user,
            activityDate__gte=startDate,
            activityDate__lte=endDate,
            valid=True
        )
        p_docs = Prefetch('documents',
            queryset=Document.objects.filter(user=user, is_certificate=True, is_thumb=False).order_by('-created'),
            to_attr='cert_docs'
        )
        qset = self.model.objects \
            .select_related('entryType', 'sponsor') \
            .filter(**filter_kwargs) \
            .exclude(entryType__name=ENTRYTYPE_NOTIFICATION) \
            .prefetch_related('tags', p_docs) \
            .order_by('-activityDate')
        saEntries = []  # list of Entry instances having CMETAG_SACME in their tags
        brcmeEntries = []
        otherSrCmeEntries = []
        creditSumByTag = {}
        otherCmeTotal = 0
        #print('Num entries: {0}'.format(qset.count()))
        try:
            for m in qset:
                credits = 0
                entry_tags = m.tags.all()
                tagids = set([t.pk for t in entry_tags])
                #tagnames = [t.name for t in entry_tags]
                #print('{0.pk} {0}|{1}'.format(m, ','.join(tagnames)))
                if satag.pk in tagids:
                    saEntries.append(m)
                    #print('-- add to saEntries')
                    #credits = m.srcme.credits -- include this?
                else:
                    if m.entryType.name == ENTRYTYPE_BRCME:
                        brcmeEntries.append(m)
                        credits = m.brcme.credits
                    else:
                        otherSrCmeEntries.append(m)
                        credits = m.srcme.credits
                    otherCmeTotal += credits
                #print('-- credits: {0}'.format(credits))
                # add credits to creditSumByTag
                for t in entry_tags:
                    if t.pk == satag.pk:
                        continue
                    creditSumByTag[t.name] = creditSumByTag.setdefault(t.name, 0) + credits
                    #print('---- {0.name} : {1}'.format(t, creditSumByTag[t.name]))
            # sum credit totals
            saCmeTotal = sum([m.srcme.credits for m in saEntries])
        except Exception:
            logger.exception('prepareDataForAuditReport exception')
        else:
            #logger.debug('saCmeTotal: {0}'.format(saCmeTotal))
            #logger.debug('otherCmeTotal: {0}'.format(otherCmeTotal))
            res = AuditReportResult(
                saEntries=saEntries,
                brcmeEntries=brcmeEntries,
                otherSrCmeEntries=otherSrCmeEntries,
                saCmeTotal=saCmeTotal,
                otherCmeTotal=otherCmeTotal,
                creditSumByTag=creditSumByTag
            )
            return res

    def sumSRCme(self, user, startDate, endDate, tag=None, untaggedOnly=False):
        """
        Total valid Srcme credits over the given time period for the given user.
        Optional filter by specific tag (cmeTag object).
        Optional filter by untagged only. This arg cannot be specified together with tag.
        """
        filter_kwargs = dict(
            valid=True,
            user=user,
            entryType__name=ENTRYTYPE_SRCME,
            activityDate__gte=startDate,
            activityDate__lte=endDate
        )
        if tag:
            filter_kwargs['tags__exact'] = tag
        qset = self.model.objects.select_related('entryType').filter(**filter_kwargs)
        if untaggedOnly:
            qset = qset.annotate(num_tags=Count('tags')).filter(num_tags=0)
        total = qset.aggregate(credit_sum=Sum('srcme__credits'))
        credit_sum = total['credit_sum']
        if credit_sum:
            return float(credit_sum)
        return 0

    def sumBrowserCme(self, user, startDate, endDate, tag=None, untaggedOnly=False):
        """
        Total valid BrowserCme credits over the given time period for the given user.
        Optional filter by specific tag (cmeTag object).
        Optional filter by untagged only. This arg cannot be specified together with tag.
        """
        filter_kwargs = dict(
            entry__valid=True,
            entry__user=user,
            entry__activityDate__gte=startDate,
            entry__activityDate__lte=endDate
        )
        if tag:
            filter_kwargs['entry__tags__exact'] = tag
        qset = BrowserCme.objects.select_related('entry').filter(**filter_kwargs)
        if untaggedOnly:
            qset = qset.annotate(num_tags=Count('entry__tags')).filter(num_tags=0)
        total = qset.aggregate(credit_sum=Sum('credits'))
        credit_sum = total['credit_sum']
        if credit_sum:
            return float(credit_sum)
        return 0


@python_2_unicode_compatible
class Entry(models.Model):
    CREDIT_CATEGORY_1 = u'1'
    CREDIT_CATEGORY_1_LABEL = AMA_PRA_CATEGORY_LABEL + u'1 Credit'
    CREDIT_OTHER = u'0'
    CREDIT_OTHER_LABEL = u'Other' # choice label in form
    CREDIT_OTHER_TAGNAME = u'non-Category 1 Credit' # in audit report
    # fields
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='entries',
        db_index=True
    )
    entryType = models.ForeignKey(EntryType,
        on_delete=models.PROTECT,
        db_index=True
    )
    sponsor = models.ForeignKey(Sponsor,
        on_delete=models.PROTECT,
        null=True,
        db_index=True
    )
    activityDate = models.DateTimeField()
    description = models.CharField(max_length=500)
    valid = models.BooleanField(default=True)
    tags = models.ManyToManyField(CmeTag, related_name='entries')
    documents = models.ManyToManyField(Document, related_name='entries')
    ama_pra_catg = models.CharField(max_length=2, blank=True, help_text='AMA PRA Category')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = EntryManager()

    def __str__(self):
        return '{0.entryType} of {0.activityDate}'.format(self)

    def asLocalTz(self):
        return self.created.astimezone(LOCAL_TZ)

    def formatTags(self):
        """Returns a comma-separated string of self.tags ordered by tag name"""
        names = [t.name for t in self.tags.all()]  # should use default ordering on CmeTag model
        return u', '.join(names)
    formatTags.short_description = "CmeTags"

    def formatNonSATags(self):
        """Returns a comma-separated string of self.tags ordered by tag name excluding SA-CME"""
        names = [t.name for t in self.tags.all() if t.name != CMETAG_SACME]  # should use default ordering on CmeTag model
        return u', '.join(names)

    def formatCreditType(self):
        """The CREDIT_OTHER is formatted for the audit report"""
        if self.ama_pra_catg == Entry.CREDIT_CATEGORY_1:
            return Entry.CREDIT_CATEGORY_1_LABEL
        if self.ama_pra_catg == Entry.CREDIT_OTHER:
            return Entry.CREDIT_OTHER_TAGNAME
        return u''


    def getCertDocReferenceId(self):
        """This expects attr cert_docs:list from prefetch_related.
        This is used by the CreateAuditReport view
        Returns referenceId for the first item in the list or empty str
        """
        if self.cert_docs:
            return self.cert_docs[0].referenceId
        return u''

    def getCertifyingAuthority(self):
        """If sponsor, use sponsor name, else
        use SELF_REPORTED_AUTHORITY
        """
        if self.sponsor:
            return self.sponsor.name
        return SELF_REPORTED_AUTHORITY

    def getNumDocuments(self):
        """Returns number of associated documents"""
        return self.documents.all().count()

    class Meta:
        verbose_name_plural = 'Entries'
        # custom permissions
        # https://docs.djangoproject.com/en/1.10/topics/auth/customizing/#custom-permissions
        permissions = (
            (PERM_VIEW_FEED, 'Can view Feed'),
            (PERM_VIEW_DASH, 'Can view Dashboard'),
            (PERM_POST_BRCME, 'Can redeem BrowserCmeOffer'),
            (PERM_POST_SRCME, 'Can post Self-reported Cme entry'),
            (PERM_PRINT_AUDIT_REPORT, 'Can print/share audit report'),
            (PERM_PRINT_BRCME_CERT, 'Can print/share BrowserCme certificate'),
        )

# Notification entry (in-feed message to user)
@python_2_unicode_compatible
class Notification(models.Model):
    entry = models.OneToOneField(Entry,
        on_delete=models.CASCADE,
        related_name='notification',
        primary_key=True
    )
    expireDate = models.DateTimeField(default=ACTIVE_OFFDATE)

    def __str__(self):
        return self.entry.activityDate

# Self-reported CME
# Earned credits are self-reported
@python_2_unicode_compatible
class SRCme(models.Model):
    entry = models.OneToOneField(Entry,
        on_delete=models.CASCADE,
        related_name='srcme',
        primary_key=True
    )
    credits = models.DecimalField(max_digits=6, decimal_places=2)

    def __str__(self):
        return str(self.credits)


# Browser CME entry
# An entry is created when a Browser CME offer is redeemed by the user
@python_2_unicode_compatible
class BrowserCme(models.Model):
    PURPOSE_DX = 0  # Diagnosis
    PURPOSE_TX = 1 # Treatment
    PURPOSE_CHOICES = (
        (PURPOSE_DX, 'DX'),
        (PURPOSE_TX, 'TX')
    )
    PLAN_EFFECT_N = 0 # no change to plan
    PLAN_EFFECT_Y = 1 # change to plan
    PLAN_EFFECT_CHOICES = (
        (PLAN_EFFECT_N, 'No change'),
        (PLAN_EFFECT_Y, 'Change')
    )
    entry = models.OneToOneField(Entry,
        on_delete=models.CASCADE,
        related_name='brcme',
        primary_key=True
    )
    offer = models.OneToOneField(BrowserCmeOffer,
        on_delete=models.PROTECT,
        related_name='brcme',
        db_index=True
    )
    credits = models.DecimalField(max_digits=5, decimal_places=2)
    url = models.URLField(max_length=500)
    pageTitle = models.TextField()
    purpose = models.IntegerField(
        default=0,
        choices=PURPOSE_CHOICES,
        help_text='DX = Diagnosis. TX = Treatment'
    )
    planEffect = models.IntegerField(
        default=0,
        choices=PLAN_EFFECT_CHOICES
    )

    def __str__(self):
        return self.url

    def formatActivity(self):
        res = urlparse(self.url)
        return res.netloc + ' - ' + self.entry.description

@python_2_unicode_compatible
class UserFeedback(models.Model):
    SNIPPET_MAX_CHARS = 80
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        db_index=True
    )
    message = models.CharField(max_length=500)
    hasBias = models.BooleanField(default=False)
    hasUnfairContent = models.BooleanField(default=False)
    reviewed = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.message

    def message_snippet(self):
        if len(self.message) > UserFeedback.SNIPPET_MAX_CHARS:
            return self.message[0:UserFeedback.SNIPPET_MAX_CHARS] + '...'
        return self.message
    message_snippet.short_description = "Message Snippet"

    def asLocalTz(self):
        return self.created.astimezone(LOCAL_TZ)

    class Meta:
        verbose_name_plural = 'User Feedback'

# Pinned Messages (different from in-feed Notification).
# Message is pinned and exactly 0 or 1 active Message exists for a user at any given time.
class PinnedMessageManager(models.Manager):
    def getLatestForUser(self, user):
        now = timezone.now()
        qset = PinnedMessage.objects.filter(user=user, startDate__lte=now, expireDate__gt=now).order_by('-created')
        if qset.exists():
            return qset[0]

@python_2_unicode_compatible
class PinnedMessage(models.Model):
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='pinnedmessages',
        db_index=True
    )
    sponsor = models.ForeignKey(Sponsor,
        on_delete=models.PROTECT,
        null=True,
        db_index=True
    )
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=1000)
    startDate = models.DateTimeField()
    expireDate = models.DateTimeField(default=ACTIVE_OFFDATE)
    launch_url = models.URLField(max_length=1000,
        help_text='A URL for the Launch button')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = PinnedMessageManager()

    def __str__(self):
        return self.title


# A Discount must be created in the Braintree Control Panel, and synced with the db.
@python_2_unicode_compatible
class Discount(models.Model):
    discountId = models.CharField(max_length=36, unique=True)
    discountType = models.CharField(max_length=40, help_text='Discount Type: lowercased')
    name = models.CharField(max_length=80)
    amount = models.DecimalField(max_digits=5, decimal_places=2, help_text=' in USD')
    numBillingCycles = models.IntegerField(default=1, help_text='Number of Billing Cycles')
    activeForType = models.BooleanField(default=False, help_text='True if this is the active discount for its type')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.discountId

    def save(self, *args, **kwargs):
        """Check that only 1 row has activeForType=True for a given discountType,
        else raise ValidationError.
        """
        qset = Discount.objects.filter(discountType=self.discountType, activeForType=True)
        if self.pk:
            qset = qset.exclude(pk=self.pk)
        if qset.exists():
            raise ValidationError("Only 1 discount can have activeForType=True for its discountType: {0}".format(self.discountType))
        else:
            super(Discount, self).save(*args, **kwargs)

    class Meta:
        ordering = ['discountType', '-created']

class SignupDiscountManager(models.Manager):

    def getDiscountForUser(self, user):
        L = user.email.split('@')
        if len(L) != 2:
            return None
        email_domain = L[1]
        qset = self.model.objects.select_related('discount').filter(
                email_domain=email_domain, expireDate__gt=user.date_joined).order_by('expireDate')
        if qset.exists():
            sd = qset[0]
            return sd.discount

@python_2_unicode_compatible
class SignupDiscount(models.Model):
    email_domain = models.CharField(max_length=40)
    discount = models.ForeignKey(Discount,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='signupdiscounts',
        help_text='Discount to be applied to first billingCycle'
    )
    expireDate = models.DateTimeField('Cutoff for user signup date [UTC]')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = SignupDiscountManager()

    class Meta:
        unique_together = ('email_domain', 'discount', 'expireDate')

    def __str__(self):
        return '{0.email_domain}|{0.discount.discountId}|{0.expireDate}'.format(self)


# An invitee is given the invitee-discount once for the first billing cycle.
# An inviter is given the inviter discount once for each invitee (upto $200 max) on the next billing cycle.
class InvitationDiscountManager(models.Manager):
    def getLatestForInviter(self, inviter):
        """Return the last modified InvitationDiscount instance for the given inviter
        or None if none exists
        """
        qset = self.model.objects.filter(inviter=inviter).select_related('invitee').order_by('-modified')
        if qset.exists():
            return qset[0]
        return None

    def sumCreditForInviter(self, inviter):
        """Get sum of discount amount earned by the given inviter
        Returns: float
        """
        qset = self.model.objects.filter(inviter=inviter, inviterDiscount__isnull=False, creditEarned=True).select_related('inviterDiscount')
        data = qset.aggregate(total=Sum('inviterDiscount__amount'))
        totalAmount = data['total']
        if totalAmount:
            return float(totalAmount)
        return 0

    def getNumCompletedForInviter(self, inviter):
        """Get the total count of completed InvitationDiscounts for the given inviter 
        Returns: int
        """
        return self.model.objects.filter(inviter=inviter, inviterDiscount__isnull=False).count()

@python_2_unicode_compatible
class InvitationDiscount(models.Model):
    invitee = models.OneToOneField(User,
        on_delete=models.CASCADE,
        primary_key=True
    )
    inviter = models.ForeignKey(User,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='inviters',
    )
    inviterDiscount = models.ForeignKey(Discount,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
        related_name='inviterdiscounts',
        help_text='Set when inviter subscription has been updated with the discount'
    )
    inviteeDiscount = models.ForeignKey(Discount,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='inviteediscounts',
    )
    inviterBillingCycle = models.PositiveIntegerField(default=1,
        help_text='Billing cycle of inviter at the time their subscription was updated.')
    creditEarned = models.BooleanField(default=False,
        help_text='True if inviter earns actual credit for this invitee as opposed to just karma.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = InvitationDiscountManager()

    def __str__(self):
        return '{0.invitee} by {0.inviter}'.format(self)

# Note: sender_batch header can include recipient_type=EMAIL
# A BatchPayout consists of 1+ payout-items, each to a specific receipient.
# A single payout-item is paid to a specific affiliate. The amount paid for the
# payout-item = sum([unset AffiliatePayout instances (one per convertee)]).
# Upon creating the BatchPayout, the batchpayout FK is set on the AffiliatePayout instances used in the sum.
# Upon updating the status of the BatchPayout, the payoutItemId/status/transactionId is also saved
# to the 1+ AffiliatePayout instances used in the sum.
class BatchPayout(models.Model):
    PENDING = 'PENDING'   # waiting to be processed
    PROCESSING = 'PROCESSING' # being processed
    SUCCESS = 'SUCCESS'   # successfully processed (but some payout items may be unclaimed/on hold0
    NEW = 'NEW'           # delayed due to internal updates
    DENIED = 'DENIED'     # No items in the batch payout were processed
    CANCELED = 'CANCELED' # status cannot occur if sender uses the API only to send payouts but can occur if web pay is used.
    UNSET = 'unset'  # default value upon row creation
    STATUS_CHOICES = (
        (PENDING, PENDING),
        (PROCESSING, PROCESSING),
        (SUCCESS, SUCCESS),
        (DENIED, DENIED),
        (NEW, NEW),
        (CANCELED, CANCELED),
        (UNSET, UNSET)
    )
    sender_batch_id = models.CharField(max_length=36, unique=True)
    email_subject = models.CharField(max_length=200)
    # fields to store response
    payout_batch_id = models.CharField(max_length=36, blank=True, help_text='PayPal-generated ID for a batch payout.')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=UNSET,
        help_text='PayPal-defined status of batch payout request')
    date_completed = models.DateTimeField(null=True, blank=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2, help_text='Batch amount paid')
    currency = models.CharField(max_length=4, blank=True, default='USD', help_text='Amount currency')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'SBID:{0.sender_batch_id}|PBID:{0.payout_batch_id}'.format(self)

# An convertee is given the invitee-discount once for the 1st billing cycle.
# An affiliate is paid the per-user bonus once the convertee begins an Active subscription.
class AffiliatePayoutManager(models.Manager):
    def calcTotalByAffiliate(self):
        """Find rows with batchpayout=null (rows that have not been processed yet).
        Group by affiliate and filter by convertee has begin Active UserSubscription status (and payment transaction exists)
        For each affiliate: total = sum(m.amount) for m in filtered_rows
        Returns dict {
            affiliate_pk:int => {
                total:Decimal,  -- amount earned by this affl
                pks:list        -- self.model pkeyids included for total
            }
        }
        """
        total_by_affl = dict() # affl.pk => {total:Decimal, pks:list}
        vqset = AffiliatePayout.objects.filter(batchpayout__isnull=True).values_list('affiliate', flat=True)
        for aff_pk in vqset:
            #print('aff_pk: {0}'.format(aff_pk))
            qset = AffiliatePayout.objects.filter(affiliate_id=aff_pk, batchpayout__isnull=True).order_by('created')
            # Filter AffiliatePayout qset by Subscription status
            filtered = []
            for m in qset:
                user_subs = UserSubscription.objects.getLatestSubscription(m.convertee)
                #if user_subs:
                if user_subs and user_subs.status == UserSubscription.ACTIVE and SubscriptionTransaction.objects.filter(subscription=user_subs).exists():
                    #print(m)
                    filtered.append(m)
            if filtered:
                total = sum([m.amount for m in filtered])
                #print('total for aff: {0}'.format(total))
                total_by_affl[aff_pk] = dict(
                    total=total,
                    pks=[m.pk for m in filtered])
        return total_by_affl


@python_2_unicode_compatible
class AffiliatePayout(models.Model):
    BLOCKED = 'BLOCKED' # item is blocked
    DENIED = 'DENIED'   # item is denied payment
    FAILED = 'FAILED'   # processing failed
    NEW = 'NEW'         # delayed due to internal updates
    ONHOLD = 'ONHOLD'   # item is on hold
    PENDING = 'PENDING' # item is awaiting payment
    REFUNDED = 'REFUNDED' # payment for the item was succesfully refunded
    RETURNED = 'RETURNED' # item is returned (recipient did not claim payment within 30 days)
    SUCCESS = 'SUCCESS'   # item is successfully processed
    UNCLAIMED = 'UNCLAIMED' # item is unclaimed (after 30 days unclaimed, status changes to RETURNED)
    UNSET = 'unset'  # default value upon row creation
    STATUS_CHOICES = (
        (PENDING, PENDING),
        (SUCCESS, SUCCESS),
        (DENIED, DENIED),
        (NEW, NEW),
        (BLOCKED, BLOCKED),
        (FAILED, FAILED),
        (ONHOLD, ONHOLD),
        (REFUNDED, REFUNDED),
        (RETURNED, RETURNED),
        (UNCLAIMED, UNCLAIMED),
        (UNSET, UNSET)
    )
    convertee = models.OneToOneField(User,
        on_delete=models.CASCADE,
        primary_key=True
    )
    affiliate = models.ForeignKey(Affiliate,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='payouts',
    )
    batchpayout= models.ForeignKey(BatchPayout,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='afflpayouts',
    )
    converteeDiscount = models.ForeignKey(Discount,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='converteediscounts',
    )
    payoutItemId = models.CharField(max_length=36, blank=True, default='',
            help_text='PayPal-generated item identifier. Exists even if there is no transactionId.')
    transactionId = models.CharField(max_length=36, blank=True, default='',
            help_text='PayPal-generated id for the transaction.')
    amount = models.DecimalField(max_digits=5, decimal_places=2, help_text='per_user bonus paid to affiliate in USD.')
    status = models.CharField(max_length=20, blank=True, choices=STATUS_CHOICES, default=UNSET,
            help_text='PayPal-defined item transaction status')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = AffiliatePayoutManager()

    def __str__(self):
        return '{0.convertee} by {0.affiliate}/{0.status}'.format(self)


# Recurring Billing Plans
# https://developers.braintreepayments.com/guides/recurring-billing/plans
# A Plan must be created in the Braintree Control Panel, and synced with the db.
@python_2_unicode_compatible
class SubscriptionPlan(models.Model):
    planId = models.CharField(max_length=36, unique=True)
    name = models.CharField(max_length=80)
    price = models.DecimalField(max_digits=6, decimal_places=2, help_text=' in USD')
    trialDays = models.IntegerField(default=0, help_text='Trial period in days')
    billingCycleMonths = models.IntegerField(default=12, help_text='Billing Cycle in months')
    discountPrice = models.DecimalField(max_digits=6, decimal_places=2, help_text='discounted price in USD')
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def monthlyPrice(self):
        return self.price/Decimal('12.0')

    def discountMonthlyPrice(self):
        return self.discountPrice/Decimal('12.0')


# User Subscription
# https://articles.braintreepayments.com/guides/recurring-billing/subscriptions
class UserSubscriptionManager(models.Manager):
    def getLatestSubscription(self, user):
        qset = UserSubscription.objects.filter(user=user).order_by('-created')
        if qset.exists():
            return qset[0]

    def getPermissions(self, user_subs):
        """Return the permissions for the group given by user_subs.display_status
        Returns: Permission queryset
        """
        g = Group.objects.get(name=user_subs.display_status)
        return g.permissions.all().order_by('codename')

    def allowNewSubscription(self, user):
        """If user has no existing subscriptions, or latest subscription is canceled/expired, then allow new subscription.
        """
        user_subs = self.getLatestSubscription(user)
        if not user_subs:
            return True
        status = user_subs.status
        return (status == UserSubscription.CANCELED or status == UserSubscription.EXPIRED)

    def findBtSubscription(self, subscriptionId):
        try:
            subscription = braintree.Subscription.find(subscriptionId)
        except braintree.exceptions.not_found_error.NotFoundError:
            return None
        else:
            return subscription

    def createBtSubscription(self, user, plan, subs_params):
        """Create Braintree subscription using the given params
        In local db:
            Create new UserSubscription instance
            Create new SubscriptionTransaction instance (if exists)
        Args:
            user: User instance
            plan: SubscriptionPlan instance
            subs_params:dict w. keys
                plan_id: BT planId of the plan
                payment_method_token:str for the Customer
                trial_duration:int (number of days of trial). If not given, uses plan default
                invitee_discount:bool If True, user.profile.inviter must be a User instance
                convertee_discount: if True, user.profile.inviter.affiliate must be an Affiliate instance
        Returns (Braintree result object, UserSubscription object)
        """
        user_subs = None
        is_invitee = False
        is_convertee = False
        discounts = [] # Discount instances to be applied
        inv_discount = None # saved to either InvitationDiscount or AffiliatePayout
        subs_price = None
        key = 'invitee_discount'
        if key in subs_params:
            is_invitee = subs_params.pop(key)
        key = 'convertee_discount'
        if key in subs_params:
            is_convertee = subs_params.pop(key)
        if is_invitee or is_convertee:
            inviter = user.profile.inviter # User instance (used below)
            if not inviter:
                raise ValueError('createBtSubscription: Invalid inviter')
            inv_discount = Discount.objects.get(discountType=INVITEE_DISCOUNT_TYPE, activeForType=True)
            discounts.append(inv_discount)
            # calculate subs_price
            subs_price = plan.discountPrice - inv_discount.amount
        # Check SignupDiscount - ensure it is only applied once
        qset = UserSubscription.objects.filter(user=user).exclude(display_status=self.model.UI_TRIAL_CANCELED)
        if not qset.exists():
            discount = SignupDiscount.objects.getDiscountForUser(user)
            if discount:
                discounts.append(discount)
                logger.info('Signup discount: {0} for user {1}'.format(discount, user))
                if not subs_price:
                    subs_price = plan.discountPrice
                subs_price -= discount.amount # subtract signup discount
        if discounts:
            # Add discounts:add key to subs_params
            subs_params['discounts'] = {
                'add': [
                    {"inherited_from_id": m.discountId} for m in discounts
                ]
            }
            logger.info('subs_price: {0}'.format(subs_price))
        result = braintree.Subscription.create(subs_params)
        logger.info('createBtSubscription result: {0.is_success}'.format(result))
        if result.is_success:
            key = 'trial_duration'
            if key in subs_params and subs_params[key] == 0:
                display_status = UserSubscription.UI_ACTIVE
            elif plan.trialDays:
                # subscription created with plan's default trial period
                display_status = UserSubscription.UI_TRIAL
            else:
                # plan has no trial period
                display_status = UserSubscription.UI_ACTIVE

            # create UserSubscription object in database
            firstDate = makeAwareDatetime(result.subscription.first_billing_date)
            startDate = result.subscription.billing_period_start_date
            if startDate:
                startDate = makeAwareDatetime(startDate)
            else:
                startDate = firstDate
            endDate = result.subscription.billing_period_end_date
            if endDate:
                endDate = makeAwareDatetime(endDate)
            else:
                endDate = startDate + relativedelta(months=plan.billingCycleMonths)
            user_subs = UserSubscription.objects.create(
                user=user,
                plan=plan,
                subscriptionId=result.subscription.id,
                display_status=display_status,
                status=result.subscription.status,
                billingFirstDate=firstDate,
                billingStartDate=startDate,
                billingEndDate=endDate,
                billingCycle=result.subscription.current_billing_cycle
            )
            if is_invitee and not InvitationDiscount.objects.filter(invitee=user).exists():
                # user can end/create subscription multiple times, but only add invitee once to InvitationDiscount.
                InvitationDiscount.objects.create(
                    inviter=inviter,
                    invitee=user,
                    inviteeDiscount=inv_discount
                )
            elif is_convertee and not AffiliatePayout.objects.filter(convertee=user).exists():
                afp_amount = inviter.affiliate.bonus*subs_price
                AffiliatePayout.objects.create(
                    convertee=user,
                    converteeDiscount=inv_discount,
                    affiliate=inviter.affiliate, # Affiliate instance
                    amount=afp_amount
                )

            # create SubscriptionTransaction object in database - if user skipped trial then an initial transaction should exist
            result_transactions = result.subscription.transactions # list
            if len(result_transactions):
                t = result_transactions[0]
                card_type = t.credit_card.get('card_type')
                card_last4 = t.credit_card.get('last_4')
                proc_auth_code=t.processor_authorization_code or ''
                subs_trans = SubscriptionTransaction.objects.create(
                        subscription=user_subs,
                        transactionId=t.id,
                        proc_auth_code=proc_auth_code,
                        proc_response_code=t.processor_response_code,
                        amount=t.amount,
                        status=t.status,
                        card_type=card_type,
                        card_last4=card_last4)
        return (result, user_subs)


    def makeActiveCanceled(self, user_subs):
        """
        Use case: User does not want to renew subscription,
        and their subscription is currently active and we have
        not reached billingEndDate.
        Model: set display_status to UI_ACTIVE_CANCELED.
        Braintree:
            1. Set never_expires = False
            2. Set number_of_billing_cycles on the subscription to the current_billing_cycle.
        Once this number is reached, the subscription will expire.
        Can raise braintree.exceptions.not_found_error.NotFoundError
        Returns Braintree result object
        """
        subscription = braintree.Subscription.find(user_subs.subscriptionId)
        # When subscription passes the billing_period_end_date, the current_billing_cycle is incremented
        # Set the max number of billing cycles. When billingEndDate is reached, the subscription will expire in braintree.
        curBillingCycle = subscription.current_billing_cycle
        if not curBillingCycle:
            numBillingCycles = 1
        else:
            numBillingCycles = curBillingCycle
        result = braintree.Subscription.update(user_subs.subscriptionId, {
            'never_expires': False,
            'number_of_billing_cycles': numBillingCycles
        });
        if result.is_success:
            # update model
            user_subs.display_status = UserSubscription.UI_ACTIVE_CANCELED
            if curBillingCycle:
                user_subs.billingCycle = curBillingCycle
            user_subs.save()
        return result

    def reactivateBtSubscription(self, user_subs, payment_token=None):
        """
        Use case: switch from UI_ACTIVE_CANCELED back to UI_ACTIVE
        while the btSubscription is still ACTIVE.
        Caller may optionally provide a payment_token with which
        to update the subscription.

        Note: This action cannot be done if the btSubscription is already
        expired/canceled - (user must create new subscription)
        Reference: https://developers.braintreepayments.com/guides/recurring-billing/manage/python
        """
        subscription = braintree.Subscription.find(user_subs.subscriptionId)
        if subscription.status != UserSubscription.ACTIVE:
            raise ValueError('BT Subscription status is: {0}'.format(subscription.status))
        subs_params = {
            'never_expires': True,
            'number_of_billing_cycles': None
        }
        curBillingCycle = subscription.current_billing_cycle
        if payment_token:
            subs_params['payment_method_token'] = payment_token
        result = braintree.Subscription.update(user_subs.subscriptionId, subs_params)
        if result.is_success:
            # update model
            user_subs.display_status = UserSubscription.UI_ACTIVE
            if curBillingCycle:
                user_subs.billingCycle = curBillingCycle
            user_subs.save()
        return result


    def terminalCancelBtSubscription(self, user_subs):
        """
        Use case: User wants to cancel while they are still in UI_TRIAL.
        Cancel Braintree subscription - this is a terminal state. Once
            canceled, a subscription cannot be reactivated.
        Update model: set display_status to UI_TRIAL_CANCELED.
        Reference: https://developers.braintreepayments.com/reference/request/subscription/cancel/python
        Can raise braintree.exceptions.not_found_error.NotFoundError
        Returns Braintree result object
        """
        result = braintree.Subscription.cancel(user_subs.subscriptionId)
        if result.is_success:
            user_subs.status = result.subscription.status
            user_subs.display_status = self.model.UI_TRIAL_CANCELED
            user_subs.save()
        return result


    def switchTrialToActive(self, user_subs, payment_token):
        """
        User is in UI_TRIAL, and their trial period
        is still not over, but user wants to upgrade
        to Active.  Cannot update existing subscription,
        need to cancel it, and create new one.
        Returns (Braintree result object, UserSubscription)
        """
        plan = user_subs.plan
        user = user_subs.user
        subs_params = {
            'plan_id': plan.planId,
            'trial_duration': 0,
            'payment_method_token': payment_token
        }
        if user.profile.inviter:
            qset = UserSubscription.objects.filter(user=user).exclude(pk=user_subs.pk)
            if not qset.exists():
                # User has no other subscription except this Trial which is to be canceled.
                # Can apply invitee discount to the new Active subscription
                if Affiliate.objects.filter(user=user.profile.inviter).exists():
                    subs_params['convertee_discount'] = True
                    logger.info('SwitchTrialToActive: apply convertee discount to new subscription for {0}'.format(user))
                else:
                    subs_params['invitee_discount'] = True
                    logger.info('SwitchTrialToActive: apply invitee discount to new subscription for {0}'.format(user))
        cancel_result = self.terminalCancelBtSubscription(user_subs)
        if cancel_result.is_success:
            # return (result, new_user_subs)
            return self.createBtSubscription(user, plan, subs_params)
        else:
            return (cancel_result, user_subs)


    def updateSubscriptionFromBt(self, user_subs, bt_subs):
        """Update UserSubscription instance from braintree Subscription object
        and save the model instance.
        """
        billingAmount = user_subs.nextBillingAmount
        user_subs.status = bt_subs.status
        if bt_subs.status == self.model.ACTIVE:
            today = timezone.now()
            if (today > user_subs.billingFirstDate):
                user_subs.display_status = self.model.UI_ACTIVE
            else:
                user_subs.display_status = self.model.UI_TRIAL
        elif bt_subs.status == self.model.PASTDUE:
            user_subs.display_status = self.model.UI_SUSPENDED
        startDate = bt_subs.billing_period_start_date
        endDate = bt_subs.billing_period_end_date
        if startDate:
            startDate = makeAwareDatetime(startDate)
            if user_subs.billingStartDate != startDate:
                user_subs.billingStartDate = startDate
        if endDate:
            endDate = makeAwareDatetime(endDate)
            if user_subs.billingEndDate != endDate:
                user_subs.billingEndDate = endDate
        user_subs.billingCycle = bt_subs.current_billing_cycle
        user_subs.nextBillingAmount = bt_subs.next_billing_period_amount
        user_subs.save()

    def updateSubscriptionForInviterDiscount(self, user_subs, invDisc):
        """Get the bt_subs for the given user_subs. If bt_subs
        has no inviter discount, then add it, else increment the
        quantity of the discount. Update the invDisc model instance
        and set inviterDiscount and inviterBillingCycle.
        Args:
            user_subs: UserSubscription instance for the inviter
            invDisc: InvitationDiscount instance
        Returns: InvitationDiscount instance (either updated invDisc or the same instance)
        """
        bt_subs = self.findBtSubscription(user_subs.subscriptionId)
        if not bt_subs:
            logger.error('updateSubscriptionForInviterDiscount: BT subscription not found for subscriptionId: {0.subscriptionId}'.format(user_subs))
            return (invDisc, False)
        # Get the discount instance (discountId must match in BT)
        discount = Discount.objects.get(discountType=INVITER_DISCOUNT_TYPE, activeForType=True)
        add_new_discount = True
        new_quantity = None
        for d in bt_subs.discounts:
            if d.id == discount.discountId:
                add_new_discount = False
                if d.quantity < INVITER_MAX_NUM_DISCOUNT:
                    # Update existing row: increment quantity
                    new_quantity = d.quantity + 1
                else:
                    logger.info('Inviter {0.user} has already earned  max discount quantity: {1}'.format(user_subs, INVITER_MAX_NUM_DISCOUNT))
                break
        subs_params = None
        if add_new_discount:
            subs_params = dict(discounts={'add': [
                    {"inherited_from_id": discount.discountId},
                ]})
            logger.info('Add {0.discountId} to user_subs for {1.user}'.format(discount, user_subs))
        elif new_quantity:
            subs_params = dict(discounts={'update': [
                    {
                        "existing_id": discount.discountId,
                        "quantity": new_quantity
                    },
                ]})
            logger.info('Update quantity of {0.discountId} in user_subs for {1.user} to {2}'.format(discount, user_subs, new_quantity))
        if subs_params:
            # Update BT subscription
            res = braintree.Subscription.update(user_subs.subscriptionId, subs_params)
            if res.is_success:
                # Set invitationDiscount.creditEarned
                invDisc.creditEarned = True
                invDisc.inviterDiscount = discount
                invDisc.inviterBillingCycle = bt_subs.current_billing_cycle
                invDisc.save()
                return (invDisc, True)
            else:
                logger.error('Update BtSubscription for {0.user} failed. Result message: {1.message}'.format(user_subs, res))
                # InvitationDiscount not updated
                return (invDisc, False)
        else:
            # Update InvitationDiscount (karma only)
            invDisc.inviterDiscount = discount
            invDisc.inviterBillingCycle = bt_subs.current_billing_cycle
            invDisc.save()
            return (invDisc, True)


    def checkTrialToActive(self, user_subs):
        """Check if user_subs is out of trial period.
            Returns: bool if user_subs was saved with new data from bt subscription.
        """
        today = timezone.now()
        saved = False
        if user_subs.display_status == self.model.UI_TRIAL and (today > user_subs.billingFirstDate):
            try:
                bt_subs = braintree.Subscription.find(user_subs.subscriptionId)
            except braintree.exceptions.not_found_error.NotFoundError:
                logger.error('checkTrialToActive: subscriptionId:{0.subscriptionId} for user {0.user} not found in Braintree.'.format(user_subs))
            else:
                self.updateSubscriptionFromBt(user_subs, bt_subs)
                saved = True
        return saved

    def updateLatestUserSubsAndTransactions(self, user):
        """Get the latest UserSubscription for the given user
        from the local db and update it from BT. Also update
        transactions for the user_subs.
        Returns: (pks of transactions_created, pks of transactions_updated)
        """
        user_subs = self.getLatestSubscription(user)
        if not user_subs:
            return
        bt_subs = self.findBtSubscription(user_subs.subscriptionId)
        if user_subs.status != bt_subs.status or user_subs.billingCycle != bt_subs.current_billing_cycle or user_subs.nextBillingAmount != bt_subs.next_billing_period_amount:
            self.updateSubscriptionFromBt(user_subs, bt_subs)
        return SubscriptionTransaction.objects.updateTransactionsFromBtSubs(user_subs, bt_subs)


    def searchBtSubscriptionsByPlan(self, planId):
        """Search Braintree subscriptions by plan.
        https://developers.braintreepayments.com/reference/request/subscription/search/python
        https://developers.braintreepayments.com/reference/response/subscription/python
        Returns Braintree collection object (list of Subscription result objects)
        """
        collection = braintree.Subscription.search(braintree.SubscriptionSearch.plan_id == planId)
        for subs in collection.items:
            logger.debug('{0.subscriptionId}|{0.status}|cycle:{0.current_billing_cycle}|{0.billing_period_start_date}|{0.billing_period_end_date}|NextAmount: {0.next_billing_period_amount}'.format(subs))
        return collection

@python_2_unicode_compatible
class UserSubscription(models.Model):
    # Braintree status choices
    # Active subscriptions will be charged on the next billing date. Subscriptions in a trial period are Active.
    ACTIVE = 'Active'
    # Cancel subscription, and no further billing will occur (terminal state).
    # Once canceled, a subscription cannot be edited or reactivated.
    CANCELED = 'Canceled'
    # Subscriptions are Expired when they have reached the specified number of billing cycles.
    EXPIRED = 'Expired'
    # If a payment for a subscription fails, the subscription status will change to Past Due.
    PASTDUE = 'Past Due'
    # Pending subscriptions are ones that have an explicit first bill date in the future.
    PENDING = 'Pending'
    STATUS_CHOICES = (
        (ACTIVE, ACTIVE),
        (CANCELED, CANCELED),
        (EXPIRED, EXPIRED),
        (PASTDUE, PASTDUE),
        (PENDING, PENDING)
    )
    # UI status values for display
    UI_TRIAL = 'Trial'
    UI_ACTIVE = 'Active'
    UI_ACTIVE_CANCELED = 'Active-Canceled'
    UI_TRIAL_CANCELED = 'Trial-Canceled'
    UI_SUSPENDED = 'Suspended'
    UI_EXPIRED = 'Expired'
    UI_STATUS_CHOICES = (
        (UI_TRIAL, UI_TRIAL),
        (UI_ACTIVE, UI_ACTIVE),
        (UI_ACTIVE_CANCELED, UI_ACTIVE_CANCELED),
        (UI_SUSPENDED, UI_SUSPENDED),
        (UI_EXPIRED, UI_EXPIRED),
        (UI_TRIAL_CANCELED, UI_TRIAL_CANCELED)
    )
    # fields
    subscriptionId = models.CharField(max_length=36, unique=True)
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='subscriptions',
    )
    plan = models.ForeignKey(SubscriptionPlan,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='subscribers',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
        help_text='Braintree-defined status')
    display_status = models.CharField(max_length=40, choices=UI_STATUS_CHOICES,
        help_text='Status for UI display')
    billingFirstDate = models.DateTimeField(null=True, blank=True, help_text='Braintree first_bill_date')
    billingStartDate = models.DateTimeField(null=True, blank=True, help_text='Braintree billing_period_start_date - regardless of status')
    billingEndDate = models.DateTimeField(null=True, blank=True, help_text='Braintree billing_period_end_date - regardless of status')
    billingCycle = models.PositiveIntegerField(default=1,
        help_text='BT current_billing_cycle')
    nextBillingAmount = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text=' BT next_billing_period_amount in USD')
    remindRenewSent = models.BooleanField(default=False, help_text='set to True upon sending of auto-renewal reminder via email')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = UserSubscriptionManager()

    def __str__(self):
        return self.subscriptionId


class SubscriptionTransactionManager(models.Manager):
    def findBtTransaction(self, transaction):
        """transaction: SubscriptionTransaction instance from db
        Returns: Braintree Transaction object / None in case of
            braintree.exceptions.not_found_error.NotFoundError
        """
        try:
            t = braintree.Transaction.find(str(transaction.transactionId))
        except braintree.exceptions.not_found_error.NotFoundError:
            return None
        else:
            return t

    def updateTransactionsFromBtSubs(self, user_subs, bt_subs):
        """Update SubscriptionTransaction(s) from braintree Subscription object"""
        created = []
        updated = []
        for t in bt_subs.transactions:
            proc_auth_code=t.processor_authorization_code or '' # convert None to empty str for db
            # does SubscriptionTransaction instance exist in db
            qset = SubscriptionTransaction.objects.filter(transactionId=t.id)
            if qset.exists():
                m = qset[0]
                doSave = False
                if m.status != t.status:
                    m.status = t.status
                    doSave = True
                if m.proc_auth_code != proc_auth_code:
                    m.proc_auth_code = proc_auth_code
                    doSave = True
                if m.proc_response_code != t.processor_response_code:
                    m.proc_response_code = t.processor_response_code
                    doSave = True
                if doSave:
                    m.save()
                    logger.info('Updated transaction {0.transactionId} from BT.'.format(m))
                    updated.append(m.pk)
            else:
                # create new
                card_type = t.credit_card.get('card_type')
                card_last4 = t.credit_card.get('last_4')
                trans_type = t.type
                if trans_type not in (SubscriptionTransaction.TYPE_SALE, SubscriptionTransaction.TYPE_CREDIT):
                    logger.warning('Unrecognized transaction type: {0}'.format(trans_type))
                m = SubscriptionTransaction.objects.create(
                        subscription=user_subs,
                        transactionId=t.id,
                        trans_type=trans_type,
                        proc_auth_code=proc_auth_code,
                        proc_response_code=t.processor_response_code,
                        amount=t.amount,
                        status=t.status,
                        card_type=card_type,
                        card_last4=card_last4)
                logger.info('Created transaction {0.transactionId} type {0.trans_type} from BT.'.format(m))
                created.append(m.pk)
        return (created, updated)


@python_2_unicode_compatible
class SubscriptionTransaction(models.Model):
    # status values
    # https://developers.braintreepayments.com/reference/general/statuses
    # The processor authorized the transaction. Not yet submitted for settlement
    AUTHORIZED = 'authorized'
    # The transaction spent too much time in the Authorized status and was marked as expired.
    AUTHORIZATION_EXPIRED = 'authorization_expired'
    # Processor did not authorize the transaction. The processor response code has information about why the transaction was declined.
    PROCESSOR_DECLINED = 'processor_declined'
    # The gateway rejected the transaction b/c fraud checks failed
    GATEWAY_REJECTED = 'gateway_rejected'
    # An error occurred when sending the transaction to the processor.
    FAILED = 'failed'
    # The transaction was voided. You can void transactions when the status is Authorized or Submitted for Settlement. After the transaction has been settled, you will have to refund the transaction instead.
    VOIDED = 'voided'
    # The transaction has been submitted for settlement and will be included in the next settlement batch. Settlement happens nightly - the exact time depends on the processor.
    SUBMITTED_FOR_SETTLEMENT = 'submitted_for_settlement'
    # The transaction is in the process of being settled. This is a transitory state. A transaction cannot be voided once it reaches Settling status, but can be refunded.
    SETTLING = 'settling'
    # The transaction has been settled.
    SETTLED = 'settled'
    # The processor settlement response code may have more information about why the transaction was declined.
    SETTLEMENT_DECLINED = 'settlement_declined'
    # transaction types
    TYPE_SALE = 'sale'
    TYPE_CREDIT = 'credit'
    # fields
    transactionId = models.CharField(max_length=36, unique=True)
    subscription = models.ForeignKey(UserSubscription,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='transactions',
    )
    amount = models.DecimalField(max_digits=6, decimal_places=2, help_text=' in USD')
    status = models.CharField(max_length=200, blank=True)
    card_type = models.CharField(max_length=100, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    proc_auth_code = models.CharField(max_length=10, blank=True, help_text='processor_authorization_code')
    proc_response_code = models.CharField(max_length=4, blank=True, help_text='processor_response_code')
    receipt_sent = models.BooleanField(default=False, help_text='set to True on sending of receipt via email')
    failure_alert_sent = models.BooleanField(default=False, help_text='set to True on sending of payment failure alert via email')
    trans_type = models.CharField(max_length=10, default='sale', help_text='sale or credit. If credit, then amount was refunded')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = SubscriptionTransactionManager()

    def __str__(self):
        return self.transactionId

    def isSale(self):
        return self.trans_type == SubscriptionTransaction.TYPE_SALE

    def isCredit(self):
        return self.trans_type == SubscriptionTransaction.TYPE_CREDIT

    def canSendReceipt(self):
        """Can send sale receipt"""
        return self.isSale() and self.status in (
                SubscriptionTransaction.SUBMITTED_FOR_SETTLEMENT,
                SubscriptionTransaction.SETTLING,
                SubscriptionTransaction.SETTLED
            )

    def canSendFailureAlert(self):
        """Can send payment failure alert"""
        return self.isSale() and self.status in (
                SubscriptionTransaction.AUTHORIZATION_EXPIRED,
                SubscriptionTransaction.FAILED,
                SubscriptionTransaction.GATEWAY_REJECTED,
                SubscriptionTransaction.PROCESSOR_DECLINED
            )

def certificate_document_path(instance, filename):
    return '{0}/uid_{1}/{2}'.format(settings.CERTIFICATE_MEDIA_BASEDIR, instance.user.id, filename)

# BrowserCme certificate - generated file
@python_2_unicode_compatible
class Certificate(models.Model):
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='certificates',
        db_index=True
    )
    referenceId = models.CharField(max_length=64,
        null=True,
        blank=True,
        unique=True,
        default=None,
        help_text='alphanum unique key generated from the certificate id')
    name = models.CharField(max_length=255, help_text='Name on certificate')
    startDate = models.DateTimeField()
    endDate = models.DateTimeField()
    credits = models.DecimalField(max_digits=6, decimal_places=2)
    document = models.FileField(upload_to=certificate_document_path)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def getAccessUrl(self):
        """Returns the front-end URL to access this certificate"""
        return "https://{0}/certificate/{1}".format(settings.SERVER_HOSTNAME, self.referenceId)

def audit_report_document_path(instance, filename):
    return '{0}/uid_{1}/{2}'.format(settings.AUDIT_REPORT_MEDIA_BASEDIR, instance.user.id, filename)

# Audit Report - raw data for the report is saved in JSONField
@python_2_unicode_compatible
class AuditReport(models.Model):
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='auditreports',
        db_index=True
    )
    certificate = models.ForeignKey(Certificate,
        on_delete=models.PROTECT,
        null=True,
        db_index=True,
        related_name='auditreports',
        help_text='BrowserCme Certificate generated for the same date range'
    )
    referenceId = models.CharField(max_length=64,
        null=True,
        blank=True,
        unique=True,
        default=None,
        help_text='alphanum unique key generated from the pk')
    name = models.CharField(max_length=255, help_text='Name/title of the report')
    startDate = models.DateTimeField()
    endDate = models.DateTimeField()
    saCredits = models.DecimalField(max_digits=6, decimal_places=2, help_text='Calculated number of SA-CME credits')
    otherCredits = models.DecimalField(max_digits=6, decimal_places=2, help_text='Calculated number of other credits')
    data = JSONField()
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.referenceId


#
# plugin models - managed by plugin_server project
#
@python_2_unicode_compatible
class AllowedHost(models.Model):
    id = models.AutoField(primary_key=True)
    hostname = models.CharField(max_length=100, unique=True, help_text='netloc only. No scheme')
    accept_query_keys = models.TextField(blank=True, default='', help_text='accepted keys in url query')
    has_paywall = models.BooleanField(blank=True, default=False, help_text='True if full text is behind paywall')
    allow_page_download = models.BooleanField(blank=True, default=True,
            help_text='False if pages under this host should not be downloaded')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_allowedhost'

    def __str__(self):
        return self.hostname

@python_2_unicode_compatible
class HostPattern(models.Model):
    id = models.AutoField(primary_key=True)
    host = models.ForeignKey(AllowedHost,
        on_delete=models.CASCADE,
        related_name='hostpatterns',
        db_index=True
    )
    eligible_site = models.ForeignKey(EligibleSite,
        on_delete=models.CASCADE,
        db_index=True)
    path_contains = models.CharField(max_length=200, blank=True, default='',
        help_text='If given, url path part must contain this term. No trailing slash.')
    path_reject = models.CharField(max_length=200, blank=True, default='',
        help_text='If given, url path part must not contain this term. No trailing slash.')
    pattern_key = models.CharField(max_length=40, help_text='valid key in URL_PATTERNS dict')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_hostpattern'
        ordering = ['host','eligible_site','pattern_key','path_contains']

    def __str__(self):
        return '{0.host}|{0.eligible_site.domain_name}|{0.pattern_key}|pc:{0.path_contains}|pr: {0.path_reject}'.format(self)

@python_2_unicode_compatible
class AllowedUrl(models.Model):
    id = models.AutoField(primary_key=True)
    host = models.ForeignKey(AllowedHost,
        on_delete=models.CASCADE,
        db_index=True
    )
    eligible_site = models.ForeignKey(EligibleSite,
        on_delete=models.CASCADE,
        db_index=True)
    url = models.URLField(max_length=MAX_URL_LENGTH, unique=True)
    valid = models.BooleanField(default=True)
    page_title = models.TextField(blank=True, default='')
    abstract = models.TextField(blank=True, default='')
    doi = models.CharField(max_length=100, blank=True,
        help_text='Digital Object Identifier e.g. 10.1371/journal.pmed.1002234')
    pmid = models.CharField(max_length=20, blank=True, help_text='PubMed Identifier (PMID)')
    pmcid = models.CharField(max_length=20, blank=True, help_text='PubMedCentral Identifier (PMCID)')
    set_id = models.CharField(max_length=500, blank=True,
        help_text='Used to group a set of URLs that point to the same resource')
    content_type = models.CharField(max_length=100, blank=True, help_text='page content_type')
    cmeTags = models.ManyToManyField(CmeTag, blank=True, related_name='aurls')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_allowedurl'

    def __str__(self):
        return self.url

class RejectedUrl(models.Model):
    id = models.AutoField(primary_key=True)
    host = models.ForeignKey(AllowedHost, db_index=True)
    url = models.URLField(max_length=MAX_URL_LENGTH, unique=True)
    starts_with = models.BooleanField(default=False, help_text='True if any sub URL under it should also be rejected')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_rejectedurl'

    def __str__(self):
        return self.url

# Requests made by plugin users for new AllowedUrl entries
@python_2_unicode_compatible
class RequestedUrl(models.Model):
    id = models.AutoField(primary_key=True)
    url = models.URLField(max_length=MAX_URL_LENGTH, unique=True)
    valid = models.NullBooleanField(default=None)
    users = models.ManyToManyField(User, through='WhitelistRequest')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'trackers_requestedurl'

    def __str__(self):
        return self.url

# User-RequestedUrl association
@python_2_unicode_compatible
class WhitelistRequest(models.Model):
    id = models.AutoField(primary_key=True)
    req_url = models.ForeignKey(RequestedUrl, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'trackers_whitelistrequest'
        unique_together = ('req_url', 'user')

    def __str__(self):
        return '{0}-{1}'.format(self.user, self.req_url.url)
