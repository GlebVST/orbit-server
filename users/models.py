from __future__ import unicode_literals
import logging
import braintree
import calendar
from collections import namedtuple
from datetime import datetime, timedelta
from dateutil.relativedelta import *
from decimal import Decimal, ROUND_HALF_UP
from hashids import Hashids
import pytz
import re
import uuid
from urlparse import urlparse
from django.conf import settings
from django.contrib.auth.models import User, Group, Permission
from django.contrib.postgres.fields import JSONField
from django.core.exceptions import ValidationError
from django.db import models, connection
from django.db.models import Q, Prefetch, Count, Sum
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible

logger = logging.getLogger('gen.models')

from common.appconstants import (
    MAX_URL_LENGTH,
    SELF_REPORTED_AUTHORITY,
    AMA_PRA_CATEGORY_LABEL,
    ALL_PERMS,
    PERM_VIEW_OFFER,
    PERM_VIEW_FEED,
    PERM_VIEW_DASH,
    PERM_POST_SRCME,
    PERM_POST_BRCME,
    PERM_DELETE_BRCME,
    PERM_EDIT_BRCME,
    PERM_PRINT_AUDIT_REPORT,
    PERM_PRINT_BRCME_CERT,
    MONTH_CME_LIMIT_MESSAGE,
    YEAR_CME_LIMIT_MESSAGE
)
#
# constants (should match the database values)
#
ENTRYTYPE_BRCME = 'browser-cme'
ENTRYTYPE_SRCME = 'sr-cme'
ENTRYTYPE_STORY_CME = 'story-cme'
ENTRYTYPE_NOTIFICATION = 'notification'
CMETAG_SACME = 'SAM/SA-CME'
COUNTRY_USA = 'USA'
DEGREE_MD = 'MD'
DEGREE_DO = 'DO'
DEGREE_NP = 'NP'
DEGREE_RN = 'RN'
SPONSOR_BRCME = 'TUSM'
ACTIVE_OFFDATE = datetime(3000,1,1,tzinfo=pytz.utc)
INVITER_DISCOUNT_TYPE = 'inviter'
INVITEE_DISCOUNT_TYPE = 'invitee'
CONVERTEE_DISCOUNT_TYPE = 'convertee'
ORG_DISCOUNT_TYPE = 'org'
BASE_DISCOUNT_TYPE = 'base'

# specialties that have SA-CME tag pre-selected on OrbitCmeOffer
SACME_SPECIALTIES = (
    'Radiology',
    'Radiation Oncology',
    'Pathology',
)

# maximum number of invites for which a discount is applied to the inviter's subscription.
INVITER_MAX_NUM_DISCOUNT = 10

LOCAL_TZ = pytz.timezone(settings.LOCAL_TIME_ZONE)
TWO_PLACES = Decimal('.01')
TEST_CARD_EMAIL_PATTERN = re.compile(r'testcode-(?P<code>\d+)')

# Q objects
Q_ADMIN = Q(username__in=('admin','radmin')) # django admin users not in auth0
Q_IMPERSONATOR = Q(is_staff=True) & ~Q_ADMIN

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
    abbrev = models.CharField(max_length=15, blank=True)
    rnCertValid = models.BooleanField(default=False, help_text='True if RN/NP certificate is valid in this state')
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

    def isNurse(self):
        """Returns True if degree is RN/NP"""
        abbrev = self.abbrev
        return abbrev == DEGREE_RN or abbrev == DEGREE_NP

    def isPhysician(self):
        """Returns True if degree is MD/DO"""
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
class Organization(models.Model):
    """Organization - groups of users
    """
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True, help_text='Org code for display')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.code


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
    socialId = models.CharField(max_length=64, blank=True, help_text='Auth0 ID')
    pictureUrl = models.URLField(max_length=1000, blank=True, help_text='Auth0 avatar URL')
    cmeTags = models.ManyToManyField(CmeTag,
            through='ProfileCmetag',
            blank=True,
            related_name='profiles')
    degrees = models.ManyToManyField(Degree, blank=True) # called primaryrole in UI
    specialties = models.ManyToManyField(PracticeSpecialty, blank=True)
    verified = models.BooleanField(default=False, help_text='User has verified their email via Auth0')
    is_affiliate = models.BooleanField(default=False, help_text='True if user is an approved affiliate')
    accessedTour = models.BooleanField(default=False, help_text='User has commenced the online product tour')
    cmeStartDate = models.DateTimeField(null=True, blank=True, help_text='Start date for CME requirements calculation')
    cmeEndDate = models.DateTimeField(null=True, blank=True, help_text='Due date for CME requirements fulfillment')
    affiliateId = models.CharField(max_length=20, blank=True, default='', help_text='If conversion, specify Affiliate ID')
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
        """Signup is complete if:
            1. user has saved a UserSubscription
        """
        if not self.user.subscriptions.exists():
            return False
        return True

    def getFullName(self):
        return u"{0} {1}".format(self.firstName, self.lastName)

    def getInitials(self):
        """Returns initials from firstName, lastName"""
        firstInitial = ''
        lastInitial = ''
        if self.firstName:
            firstInitial = self.firstName[0].upper()
        if self.lastName:
            lastInitial = self.lastName[0].upper()
        if firstInitial and lastInitial:
            return u"{0}.{1}.".format(firstInitial, lastInitial)
        return ''

    def getFullNameAndDegree(self):
        degrees = self.degrees.all()
        degree_str = ", ".join(str(degree.abbrev) for degree in degrees)
        return u"{0} {1}, {2}".format(self.firstName, self.lastName, degree_str)

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
        return ProfileCmetag.filter(profile=self, is_active=True)

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
    displayLabel = models.CharField(max_length=60, blank=True, default='', help_text='identifying label used in display')
    paymentEmail = models.EmailField(help_text='Valid email address to be used for Payouts.')
    bonus = models.DecimalField(max_digits=3, decimal_places=2, default=0.15, help_text='Fractional multipler on fully discounted priced paid by convertee')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '{0.displayLabel}'.format(self)

class AffiliateDetail(models.Model):
    affiliate = models.ForeignKey(Affiliate,
        on_delete=models.CASCADE,
        related_name='affdetails',
        db_index=True
    )
    affiliateId = models.CharField(max_length=20, unique=True, help_text='Affiliate ID')
    active = models.BooleanField(default=True)
    personalText = models.TextField(blank=True, default='', help_text='Custom personal text for display')
    photoUrl = models.URLField(max_length=500, blank=True, help_text='Link to photo')
    jobDescription = models.TextField(blank=True)
    og_title = models.TextField(blank=True, default='Orbit', help_text='Value for og:title metatag')
    og_description = models.TextField(blank=True, default='', help_text='Value for og:description metatag')
    og_image = models.URLField(max_length=500, blank=True, help_text='URL for og:image metatag')
    redirect_page = models.CharField(max_length=80, blank=True, default='', help_text='Name of HTML page for redirect - e.g. orbitPA.html')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '{0.affiliate}|{0.affiliateId}'.format(self)

class LicenseType(models.Model):
    name = models.CharField(max_length=10, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

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
    license_type = models.ForeignKey(LicenseType,
        on_delete=models.CASCADE,
        related_name='statelicenses',
        db_index=True
    )
    license_no = models.CharField(max_length=40, blank=True, default='',
            help_text='License number')
    expiryDate = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user','state','license_type','license_no')

    def __str__(self):
        return self.license_no

    def getLabelForCertificate(self):
        """Returns str e.g. California RN License #12345
        """
        label = "{0.state.name} {0.license_type.name} License #{0.license_no}".format(self)
        return label

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
        Returns: [{
            token:str alphanumeric value that references a specific payment method in the Vault,
            number:str masked number of card (e.g. '371449******8431')
            type:str card type (e.g. American Express)
            expiry:str card expiration in mm/yyyy format (e.g. 06/2021)
            expired:boolean True if card is expired, else False
        },]
        """
        bc = self.findBtCustomer(customer)
        results = [{
            "token": m.token,
            "number": m.masked_number,
            "type": m.card_type,
            "expiry": m.expiration_date,
            "expired": m.expired
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


# A Story is broadcast to many users.
# The launch_url must be customized to include the user id when sending
# it in the response for a given user.
@python_2_unicode_compatible
class Story(models.Model):
    sponsor = models.ForeignKey(Sponsor,
        on_delete=models.PROTECT,
        db_index=True
    )
    title = models.CharField(max_length=500)
    description = models.CharField(max_length=2000)
    credits = models.DecimalField(max_digits=4, decimal_places=2, default=1, blank=True,
        help_text='CME credits to be awarded upon completion (default = 1)')
    startDate = models.DateTimeField()
    expireDate = models.DateField(help_text='Expiration date for display')
    endDate = models.DateTimeField(help_text='Expiration timestamp used by server')
    launch_url = models.URLField(max_length=1000, help_text='Form URL')
    entry_url = models.URLField(max_length=1000, help_text='Article URL will be copied to the feed entries.')
    entry_title = models.CharField(max_length=1000, help_text='Article title will be copied to the feed entries.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Stories'

    def __str__(self):
        return self.title


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
        Note that for some users, their br-cme entries will fall into the saEntries bucket.
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
                    logger.debug('-- Add entry {0.pk} {0.entryType} to saEntries'.format(m))
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
            saCmeTotal = sum([m.getCredits() for m in saEntries])
        except Exception:
            logger.exception('prepareDataForAuditReport exception')
        else:
            logger.debug('saCmeTotal: {0}'.format(saCmeTotal))
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


    def sumStoryCme(self, user, startDate, endDate):
        """
        Total valid StoryCme credits over the given time period for the given user.
        """
        filter_kwargs = dict(
            valid=True,
            user=user,
            entryType__name=ENTRYTYPE_STORY_CME,
            activityDate__gte=startDate,
            activityDate__lte=endDate
        )
        qset = self.model.objects.select_related('entryType').filter(**filter_kwargs)
        total = qset.aggregate(credit_sum=Sum('storycme__credits'))
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
        return '{0.pk}|{0.entryType}|{0.user}|{0.activityDate}'.format(self)

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

    def getCredits(self):
        """Returns credit:Decimal value"""
        if self.entryType.name == ENTRYTYPE_SRCME:
            return self.srcme.credits
        if self.entryType.name == ENTRYTYPE_BRCME:
            return self.brcme.credits
        if self.entryType.name == ENTRYTYPE_STORY_CME:
            return self.storycme.credits
        return 0

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
            (PERM_DELETE_BRCME, 'Can delete BrowserCme entry'),
            (PERM_EDIT_BRCME, 'Can edit BrowserCme entry'),
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


class BrowserCmeManager(models.Manager):

    def hasEarnedMonthLimit(self, user_subs, year, month):
        """Returns True if user has reached the monthly limit set by user_subs.plan
        Note: this should only be called for LimitedCme plans.
        Args:
            user_subs: UserSubscription instance
            year:int
            month:int
        """
        user = user_subs.user
        plan = user_subs.plan
        qs = self.model.objects.select_related('entry').filter(
            entry__user=user,
            entry__created__year=year,
            entry__created__month=month,
            entry__valid=True
        ).aggregate(cme_total=Sum('credits'))
        return qs['cme_total'] >= plan.maxCmeMonth

    def hasEarnedYearLimit(self, user_subs, year):
        """Returns True if user has reached the monthly limit set by user_subs.plan
        Note: this should only be called for LimitedCme plans.
        Args:
            user_subs: UserSubscription instance
            dt: datetime - used for year count
        """
        user = user_subs.user
        plan = user_subs.plan
        qs = self.model.objects.select_related('entry').filter(
            entry__user=user,
            entry__created__year=year,
            entry__valid=True
        ).aggregate(cme_total=Sum('credits'))
        return qs['cme_total'] >= plan.maxCmeYear


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
    offerId = models.PositiveIntegerField(null=True, default=None)
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
    planText = models.CharField(max_length=500, blank=True, default='',
            help_text='Optional explanation of changes to clinical plan'
    )
    objects = BrowserCmeManager()

    def __str__(self):
        return self.url

    def formatActivity(self):
        res = urlparse(self.url)
        return res.netloc + ' - ' + self.entry.description

# Story CME entry
# An entry is created by a script for users who completed a particular Story
@python_2_unicode_compatible
class StoryCme(models.Model):
    entry = models.OneToOneField(Entry,
        on_delete=models.CASCADE,
        related_name='storycme',
        primary_key=True
    )
    story = models.ForeignKey(Story,
        on_delete=models.PROTECT,
        related_name='storycme',
        db_index=True
    )
    credits = models.DecimalField(max_digits=5, decimal_places=2)
    url = models.URLField(max_length=500)
    title = models.TextField()

    def __str__(self):
        return self.url


@python_2_unicode_compatible
class UserFeedback(models.Model):
    SNIPPET_MAX_CHARS = 80
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        db_index=True
    )
    entry = models.OneToOneField(Entry,
        on_delete=models.SET_NULL,
        related_name='feedback',
        null=True,
        blank=True,
        default=None
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

# This model is no longer used for Orbit Stories, it has been superseded by Story. Its fields need to be changed once we use it for user-specified PinnedMessages.
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

    def getForUser(self, user):
        """Returns SignupDiscount instance/None for the given user"""
        L = user.email.split('@')
        if len(L) != 2:
            return None
        email_domain = L[1]
        qset = self.model.objects.select_related('discount').filter(
                email_domain=email_domain, expireDate__gt=user.date_joined).order_by('expireDate')
        if qset.exists():
            return qset[0]

@python_2_unicode_compatible
class SignupDiscount(models.Model):
    email_domain = models.CharField(max_length=40)
    organization = models.ForeignKey(Organization,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='signupdiscounts'
    )
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
        return '{0.organization}|{0.email_domain}|{0.discount.discountId}|{0.expireDate}'.format(self)


@python_2_unicode_compatible
class SignupEmailPromo(models.Model):
    email = models.EmailField(unique=True)
    first_year_price = models.DecimalField(max_digits=5, decimal_places=2, help_text='First year promotional price')
    display_label = models.CharField(max_length=60, blank=True, default='',
            help_text='Display label shown to the user in the discount screen')
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return '{0.email}|{0.first_year_price}'.format(self)


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


class SubscriptionPlanKey(models.Model):
    name = models.CharField(max_length=64, unique=True,
            help_text='Must be unique. Must match the landing_key in the pricing page URL')
    description = models.TextField(blank=True, default='')
    degree = models.ForeignKey(Degree,
        on_delete=models.PROTECT,
        db_index=True,
        related_name='plan_keys'
    )
    specialty = models.ForeignKey(PracticeSpecialty,
        null=True,
        blank=True,
        default=None,
        on_delete=models.PROTECT,
        db_index=True,
        related_name='plan_keys'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class SubscriptionPlanManager(models.Manager):
    def makePlanId(self, name):
        """Create a planId based on name and hashid of next pk
        This is used by Admin interface to auto-set planId.
        """
        HASHIDS_ALPHABET = 'abcdefghijklmnopqrstuvwxyz1234567890' # lowercase + digits
        SALT = 'SubscriptionPlan'
        MAX_NAME_LENGTH = 32
        cursor = connection.cursor()
        cursor.execute("select nextval('users_subscriptionplan_id_seq')")
        result = cursor.fetchone()
        next_pk = result[0]+1
        #print('next_pk: {0}'.format(next_pk))
        hashgen = Hashids(
            salt=SALT,
            alphabet=HASHIDS_ALPHABET,
            min_length=4
        )
        hash_pk = hashgen.encode(next_pk)
        cleaned_name = '-'.join(name.strip().lower().split())
        if len(cleaned_name) > MAX_NAME_LENGTH:
            cleaned_name = cleaned_name[0:MAX_NAME_LENGTH]
        return cleaned_name + '-{0}'.format(hash_pk)


# Recurring Billing Plans
# https://developers.braintreepayments.com/guides/recurring-billing/plans
# A Plan must be created in the Braintree Control Panel, and synced with the db.
@python_2_unicode_compatible
class SubscriptionPlan(models.Model):
    planId = models.CharField(max_length=36,
            unique=True,
            help_text='Unique. No whitespace. Must be in sync with the actual plan in Braintree')
    name = models.CharField(max_length=80,
            help_text='Internal Plan name (alphanumeric only). Must match value in Braintree. Will be used to set planId.')
    display_name = models.CharField(max_length=40,
            help_text='Display name - what the user sees (e.g. Standard).')
    price = models.DecimalField(max_digits=6, decimal_places=2, help_text=' in USD')
    trialDays = models.IntegerField(default=7,
            help_text='Trial period in days')
    billingCycleMonths = models.IntegerField(default=12,
            help_text='Billing Cycle in months')
    discountPrice = models.DecimalField(max_digits=6, decimal_places=2,
            help_text='discounted price in USD')
    active = models.BooleanField(default=True)
    plan_key = models.ForeignKey(SubscriptionPlanKey,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_index=True,
        related_name='plans',
    )
    upgrade_plan = models.ForeignKey('self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
        related_name='upgrade_plans',
    )
    downgrade_plan = models.ForeignKey('self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
        related_name='downgrade_plans',
    )
    maxCmeMonth = models.PositiveIntegerField(
        default=0,
        help_text='Maximum allowed CME per month. 0 for unlimited rate.')
    maxCmeYear = models.PositiveIntegerField(
        default=0,
        help_text='Maximum allowed CME per year. 0 for unlimited total.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = SubscriptionPlanManager()

    def __str__(self):
        return self.name

    def monthlyPrice(self):
        """returns formatted str"""
        return "{0:.2f}".format(self.price/Decimal('12.0'))

    def discountMonthlyPrice(self):
        """returns formatted str"""
        return "{0:.2f}".format(self.discountPrice/Decimal('12.0'))

    def isUnlimitedCme(self):
        """True if this is an un-limited plan, else False"""
        return self.maxCmeMonth == 0 and self.maxCmeYear == 0

    def isLimitedCmeRate(self):
        """True if this is an limited CME rate plan, else False"""
        return self.maxCmeMonth > 0

# User Subscription
# https://articles.braintreepayments.com/guides/recurring-billing/subscriptions
class UserSubscriptionManager(models.Manager):
    def getLatestSubscription(self, user):
        qset = UserSubscription.objects.filter(user=user).order_by('-created')
        if qset.exists():
            return qset[0]

    def getPermissions(self, user_subs):
        """Return the permissions for the group given by user_subs.display_status
        Returns: tuple (Permission queryset, is_brcme_month_limit, is_brcme_year_limit)
        """
        is_brcme_month_limit = False
        is_brcme_year_limit = False
        g = Group.objects.get(name=user_subs.display_status)
        if user_subs.plan.isUnlimitedCme():
            qs1 = g.permissions.all()
            qs2 = Permission.objects.filter(codename=PERM_DELETE_BRCME)
            qset = qs1.union(qs2).order_by('codename')
        else:
            filter_kwargs = {}
            user = user_subs.user
            now = timezone.now()
            if user_subs.plan.isLimitedCmeRate():
                is_brcme_month_limit = BrowserCme.objects.hasEarnedMonthLimit(user_subs, now.year, now.month)
            is_brcme_year_limit = BrowserCme.objects.hasEarnedYearLimit(user_subs, now.year)
            if is_brcme_month_limit or is_brcme_year_limit:
                qset = g.permissions.exclude(codename=PERM_POST_BRCME).order_by('codename')
            else:
                qset = g.permissions.all().order_by('codename')
        return (qset, is_brcme_month_limit, is_brcme_year_limit)


    def serialize_permissions(self, user, user_subs):
        """This is used by auth_views and payment_views to return
        the allowed permissions for the user in the response.
        Returns list of dicts: [{codename:str, allowed:bool}]
        for the permissions in appconstants.ALL_PERMS.
        Returns:dict {
            permissions:list of dicts {codename, allow:bool},
            brcme_limit:dict {
                is_year_limit:bool
                is_month_limit:bool
            }
        }
        """
        allowed_codes = []
        is_brcme_month_limit = False
        is_brcme_year_limit = False
        # get any special admin groups that user is a member of
        for g in user.groups.all():
            allowed_codes.extend([p.codename for p in g.permissions.all()])
        if user_subs:
            qset, is_brcme_month_limit, is_brcme_year_limit = self.getPermissions(user_subs) # Permission queryset
            allowed_codes.extend([p.codename for p in qset])
        allowed_codes = set(allowed_codes)
        perms = [{
                'codename': codename,
                'allow': codename in allowed_codes
            } for codename in ALL_PERMS]
        data = {
            'permissions': perms,
            'brcme_limit': {
                'is_year_limit': is_brcme_year_limit,
                'is_month_limit': is_brcme_month_limit
            }
        }
        return data


    def allowNewSubscription(self, user):
        """If user has no existing subscriptions, or latest subscription is canceled/expired/pastdue, then allow new subscription.
        For pastdue: the existing subs must be canceled first.
        """
        user_subs = self.getLatestSubscription(user)
        if not user_subs:
            return True
        status = user_subs.status
        return (status == UserSubscription.CANCELED or status == UserSubscription.EXPIRED or status == UserSubscription.PASTDUE)

    def findBtSubscription(self, subscriptionId):
        try:
            subscription = braintree.Subscription.find(subscriptionId)
        except braintree.exceptions.not_found_error.NotFoundError:
            return None
        else:
            return subscription

    def createSubscriptionFromBt(self, user, plan, bt_subs):
        """Handle the result of calling braintree.Subscription.create
        Args:
            user: User instance
            plan: SubscriptionPlan instance
            bt_subs: braintree Subscription object
        Create new UserSubscription instance for the given user, plan
        Create new SubscriptionTransaction if exist
        Returns UserSubscription instance
        """
        user_subs = None
        if bt_subs.trial_duration == 0:
            display_status = UserSubscription.UI_ACTIVE
        elif plan.trialDays:
            # subscription created with plan's default trial period
            display_status = UserSubscription.UI_TRIAL
        else:
            # plan has no trial period
            display_status = UserSubscription.UI_ACTIVE

        # create UserSubscription object in database
        firstDate = makeAwareDatetime(bt_subs.first_billing_date)
        startDate = bt_subs.billing_period_start_date
        if startDate:
            startDate = makeAwareDatetime(startDate)
        else:
            startDate = firstDate
        endDate = bt_subs.billing_period_end_date
        if endDate:
            endDate = makeAwareDatetime(endDate)
        else:
            endDate = startDate + relativedelta(months=plan.billingCycleMonths)
        user_subs = UserSubscription.objects.create(
            user=user,
            plan=plan,
            subscriptionId=bt_subs.id,
            display_status=display_status,
            status=bt_subs.status,
            billingFirstDate=firstDate,
            billingStartDate=startDate,
            billingEndDate=endDate,
            billingCycle=bt_subs.current_billing_cycle
        )
        # create SubscriptionTransaction object in database - if user skipped trial then an initial transaction should exist
        result_transactions = bt_subs.transactions # list
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
        return user_subs

    def getDiscountsForNewSubscription(self, user):
        """This returns the list of discounts for the user for his/her first Active subscription.
        If called by createBtSubscription, then it should be called like so:
        qset = UserSubscription.objects.filter(user=user).exclude(display_status=self.model.UI_TRIAL_CANCELED)
        if not qset.exists():
            call this method to get the discounts
        Otherwise can be called even after user has started Active Subs for other purpose (such as receipt).
        Returns list of dicts:
        { discount:Discount instance, discountType:str, displayLabel:str }
        """
        is_invitee = False
        is_convertee = False
        discounts = [] # Discount instances to be applied
        profile = user.profile
        if profile.inviter:
            # Check if inviter is an affiliate
            inviter = profile.inviter
            if Affiliate.objects.filter(user=inviter).exists():
                is_convertee = True
            else:
                is_invitee = True
        if is_invitee or is_convertee:
            inv_discount = Discount.objects.get(discountType=INVITEE_DISCOUNT_TYPE, activeForType=True)
            if is_invitee:
                discountType = INVITEE_DISCOUNT_TYPE
                displayLabel = inviter.profile.getFullName()
            else:
                discountType = CONVERTEE_DISCOUNT_TYPE
                affl = Affiliate.objects.get(user=inviter)
                displayLabel = affl.displayLabel
            discounts.append({
                'discount': inv_discount,
                'discountType': discountType,
                'displayLabel': displayLabel
            })
        sd = SignupDiscount.objects.getForUser(user)
        if sd:
            discounts.append({
                'discount': sd.discount,
                'discountType': ORG_DISCOUNT_TYPE,
                'displayLabel': sd.organization.code
            })
        return discounts

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
        qset = UserSubscription.objects.filter(user=user).exclude(display_status=self.model.UI_TRIAL_CANCELED)
        is_signup = not qset.exists() # if True, this will be the first Active subs for the user
        # If user's email exists in SignupEmailPromo then it overrides any other discounts
        if is_signup and SignupEmailPromo.objects.filter(email=user.email).exists():
            promo = SignupEmailPromo.objects.get(email=user.email)
            subs_price = promo.first_year_price
            baseDiscount = Discount.objects.get(discountType=BASE_DISCOUNT_TYPE, activeForType=True)
            discount_amount = plan.discountPrice - subs_price
            # Add discounts:add key to subs_params
            subs_params['discounts'] = {
                'add': [
                    {
                        "inherited_from_id": baseDiscount.discountId,
                        "amount": discount_amount
                    }
                ]
            }
            logger.info('SignupEmailPromo subs_price: {0}'.format(subs_price))
        else:
            if is_invitee or is_convertee:
                inv_discount = Discount.objects.get(discountType=INVITEE_DISCOUNT_TYPE, activeForType=True)
                discounts.append(inv_discount)
                # calculate subs_price
                subs_price = plan.discountPrice - inv_discount.amount
            if is_signup:
                sd = SignupDiscount.objects.getForUser(user)
                if sd:
                    discount = sd.discount
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
                logger.info('Discounted subs_price: {0}'.format(subs_price))
        result = braintree.Subscription.create(subs_params)
        logger.info('createBtSubscription result: {0.is_success}'.format(result))
        if result.is_success:
            user_subs = self.createSubscriptionFromBt(user, plan, result.subscription)
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
        return (result, user_subs)

    def createBtSubscriptionWithTestAmount(self, user, plan, subs_params):
        """Create Braintree subscription with a given test amount in order to test a particular transaction outcome.
        Args:
            user: User instance
            plan: SubscriptionPlan instance
            subs_params:dict w. keys
                plan_id: BT planId of the plan
                payment_method_token:str for the Customer
                code:integer corresponding to a processor response code (e.g. 200x)
                trial_duration:int - at least 1 in order to delay the card being charged and simulate PASTDUE status
        """
        user_subs = None
        response_code = subs_params.pop('code')
        if not response_code or (response_code < 2000) or (response_code > 3000):
            raise ValueError('Invalid response_code: {0}'.format(response_code))
        subs_params['price'] = Decimal(response_code)
        subs_params['options'] = {
            'do_not_inherit_add_ons_or_discounts': True
        }
        logger.debug(subs_params)
        result = braintree.Subscription.create(subs_params)
        logger.info('createBtSubscriptionWithTestAmount result: {0.is_success}'.format(result))
        if result.is_success:
            bt_subs = result.subscription
            #print('SubscriptionId: {0.id} Status:{0.status}'.format(bt_subs))
            new_user_subs = self.createSubscriptionFromBt(user, plan, result.subscription)
            return (result, new_user_subs)
        else:
            return (result, None)


    def getDiscountAmountForUpgrade(self, old_plan, new_plan, billingCycle, billingDay, numDaysInYear):
        """Calculate the discount amount to be used as the update amount on the
        new plan's first-year-dicountId.
        Args:
            old_plan: current (lower-priced) Plan
            new_plan: new (higher-priced) Plan
            billingCycle: int >= 1. If 1, user is eligible for a pro-rated first year discount on the new plan
            billingDay: int 1-365/366.  day in the current billing cycle on the old plan
            numDaysInYear:int either 365 or 366
        Returns: (owed:Decimal, discount_amount:Decimal)
        """
        if billingCycle == 1:
            # user in first year
            daysLeft = Decimal(numDaysInYear) - billingDay # days left in the old billing cycle
            cf = Decimal(numDaysInYear*1.0) # conversion factor to get daily plan price
            old_discount_price = old_plan.discountPrice/cf # daily discounted price
            new_discount_price = new_plan.discountPrice/cf # daily discounted price
            new_full_price = new_plan.price/cf # daily discounted price
            # amount owed at the old plan discounted price
            old_plan_discounted_amount = old_discount_price*(billingDay-1)
            # amount owed at the new plan discounted price
            new_plan_discounted_amount = new_discount_price*(daysLeft)
            # amount owed at the new plan full price
            new_plan_full_amount = new_full_price*(billingDay-1)
            total = old_plan_discounted_amount + new_plan_discounted_amount + new_plan_full_amount
            # owed = total - amount_already_paid (omitting any signup discounts b/c user earned that regardless of upgrade)
            owed = total - old_plan.discountPrice
            discount_amount = new_plan.price - owed
            logger.debug('total   : {0}'.format(total))
            logger.debug('owed    : {0}'.format(owed))
            logger.debug('discount: {0}'.format(discount_amount))
        else:
            # user in post-first year
            # the nominal amount paid (omitting any inviter discounts b/c user earned that regardless of upgrade)
            discount_amount = old_plan.price
            owed = new_plan.price - discount_amount
        return (owed, discount_amount)


    def upgradePlan(self, user_subs, new_plan, payment_token):
        """This is called to upgrade the user to a higher-priced plan (e.g. Standard to Plus).
        Cancel existing subscription, and create new one.
        If the old subscription had some discounts to be applied at the next cycle, and the discount total is less
        that is what is owed for upgrade, then apply these discounts to the new subscription.
        Returns (Braintree result object, UserSubscription)
        """
        if settings.ENV_TYPE == settings.ENV_PROD:
            # In test env, we deliberately make db different from bt (e.g. to test suspended accounts)
            bt_subs = self.findBtSubscription(user_subs.subscriptionId)
            if not bt_subs:
                raise ValueError('upgradePlan BT subscription not found for subscriptionId: {0.subscriptionId}'.format(user_subs))
            self.updateSubscriptionFromBt(user_subs, bt_subs)
        user = user_subs.user
        old_plan = user_subs.plan
        if user_subs.display_status in (UserSubscription.UI_TRIAL, UserSubscription.UI_TRIAL_CANCELED):
            return self.switchTrialToActive(user_subs, payment_token, new_plan)
        # Get discountId for plan (must exist in Braintree)
        newPlanDiscountId = 'firstyear-' + str(int(new_plan.price - new_plan.discountPrice))
        discount_amount = None
        now = timezone.now()
        if user_subs.status == UserSubscription.EXPIRED:
            # user_subs is already in a terminal state
            owed = new_plan.price
            # this value will be used to override the default plan first-year discount
            discount_amount = 0
        elif user_subs.status == UserSubscription.CANCELED:
            # This method expects the user_subs to be canceled already
            owed = new_plan.discountPrice
            discounts = UserSubscription.objects.getDiscountsForNewSubscription(user)
            for d in discounts:
                owed -= d['discount'].amount
            discount_amount = new_plan.price - owed
            logger.debug('owed    : {0}'.format(owed))
            logger.debug('discount: {0}'.format(discount_amount))
        else:
            # vars needed to calculate discount_amount
            old_billingStartDate = user_subs.billingStartDate
            old_billingCycle = user_subs.billingCycle
            old_nextBillingAmount = old_plan.price
            if user_subs.display_status == UserSubscription.UI_ACTIVE:
                old_nextBillingAmount = user_subs.nextBillingAmount
            # cancel existing subscription
            cancel_result = self.terminalCancelBtSubscription(user_subs)
            if not cancel_result.is_success:
                logger.warning('upgradePlan: Cancel old subscription failed for {0.subscriptionId} with message: {1.message}'.format(user_subs, cancel_result))
                return (cancel_result, user_subs)
            # Calculate discount_amount for the new subscription
            td = now - old_billingStartDate
            billingDay = Decimal(td.days)
            if billingDay == 0:
                billingDay = 1
            numDaysInYear = 365 if not calendar.isleap(now.year) else 366
            owed, discount_amount = self.getDiscountAmountForUpgrade(old_plan, new_plan, old_billingCycle, billingDay, numDaysInYear)
            logger.info('upgradePlan old_subs:{0.subscriptionId}|billingCycle={1}|billingDay={2}|discount={3}|owed={4}.'.format(
                user_subs,
                old_billingCycle,
                billingDay,
                discount_amount.quantize(TWO_PLACES, ROUND_HALF_UP),
                owed.quantize(TWO_PLACES, ROUND_HALF_UP)
            ))
            if (user_subs.display_status == UserSubscription.UI_ACTIVE) and (old_plan.price > old_nextBillingAmount):
                # user had earned some discounts that would have been applied to the next billing cycle on their old plan
                # (Active-Canceled users forfeited any earned discounts because they don't have a nextBillingAmount)
                earned_discount_amount = old_plan.price - old_nextBillingAmount
                # check if can apply the earned_discount_amount right now
                t = discount_amount + earned_discount_amount
                if t < new_plan.price:
                    discount_amount = t
                    owed -= earned_discount_amount
                    logger.info('Apply earned_discount={0}|New owed:{1}'.format(
                        earned_discount_amount.quantize(TWO_PLACES, ROUND_HALF_UP),
                        owed.quantize(TWO_PLACES, ROUND_HALF_UP)
                    ))
                else:
                    # Defer the earned discount to the next billingCycle on the new subscription
                    ead = earned_discount_amount.quantize(TWO_PLACES, ROUND_HALF_UP)
                    logger.info('Defer earned_discount={0} from user_subs {1.subscriptionId}'.format(ead, user_subs))
                    user.customer.balance += ead
                    user.customer.save()
        # Create new subscription
        subs_params = {
            'plan_id': new_plan.planId,
            'trial_duration': 0,
            'payment_method_token': payment_token,
            'discounts': {
                'update': [
                    {
                        'existing_id': newPlanDiscountId,
                        'amount': discount_amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                    }
                ]
            }
        }
        result = braintree.Subscription.create(subs_params)
        if result.is_success:
            logger.info('upgradePlan result: {0.is_success}'.format(result))
            new_user_subs = self.createSubscriptionFromBt(user, new_plan, result.subscription)
            return (result, new_user_subs)
        else:
            logger.warning('upgradePlan result: {0.is_success}'.format(result))
            return (result, None)


    def setExpireAtBillingCycleEnd(self, user_subs):
        """Use case: to make the user_subs expire at the end of the current_billing_cycle.
        Braintree:
            1. Set never_expires = False
            2. Set number_of_billing_cycles on the subscription to the current_billing_cycle.
        Once this number is reached, the subscription will expire.
        Can raise braintree.exceptions.not_found_error.NotFoundError
        Returns Braintree result object
        """
        bt_subs = braintree.Subscription.find(user_subs.subscriptionId)
        # When subscription passes the billing_period_end_date, the current_billing_cycle is incremented
        # Set the max number of billing cycles. When billingEndDate is reached, the subscription will expire in braintree.
        curBillingCycle = bt_subs.current_billing_cycle
        if not curBillingCycle:
            numBillingCycles = 1
        else:
            numBillingCycles = curBillingCycle
        result = braintree.Subscription.update(user_subs.subscriptionId, {
            'never_expires': False,
            'number_of_billing_cycles': numBillingCycles
        })
        return result


    def makeActiveCanceled(self, user_subs):
        """
        Use case: User does not want to renew subscription.
        Update BT subscription and set never_expires=False and number_of_billing_cycles to current cycle.
        Update model instance: set display_status = UI_ACTIVE_CANCELED
        Returns Braintree result object
        """
        result = self.setExpireAtBillingCycleEnd(user_subs)
        if result.is_success:
            user_subs.display_status = UserSubscription.UI_ACTIVE_CANCELED
            user_subs.save()
        return result


    def makeActiveDowngrade(self, user_subs):
        """
        Use case: User is currently in Plus, and wants to downgrade at end of current billing cycle.
        Update BT subscription and set never_expires=False and number_of_billing_cycles to current cycle.
        Update model instance: set display_status = UI_ACTIVE_DOWNGRADE
        Need separate management task that creates new subscription in Standard at end of the billing cycle.
        Returns Braintree result object
        """
        # find the downgrade_plan for the current plan
        downgrade_plan = user_subs.plan.downgrade_plan
        if not downgrade_plan:
            raise ValueError('No downgrade_plan found for: {0}/{0.plan}'.format(user_subs))
        else:
            logger.debug('makeActiveDowngrade to {0}/{0.planId} for user_subs {1}'.format(downgrade_plan, user_subs))
            result = self.setExpireAtBillingCycleEnd(user_subs)
            if result.is_success:
                user_subs.display_status = UserSubscription.UI_ACTIVE_DOWNGRADE
                user_subs.next_plan = downgrade_plan
                user_subs.save()
            return result


    def reactivateBtSubscription(self, user_subs, payment_token=None):
        """
        Use cases:
            1. switch from UI_ACTIVE_CANCELED back to UI_ACTIVE
            2. switch from UI_ACTIVE_DOWNGRADE back to UI_ACTIVE.
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
        Cancel Braintree subscription - this is a terminal state. Once
            canceled, a subscription cannot be reactivated.
        Update instance: set display_status to:
            UI_TRIAL_CANCELED if previous display_status was UI_TRIAL, else to UI_EXPIRED.
        Reference: https://developers.braintreepayments.com/reference/request/subscription/cancel/python
        Can raise braintree.exceptions.not_found_error.NotFoundError
        Returns Braintree result object
        """
        old_display_status = user_subs.display_status
        result = braintree.Subscription.cancel(user_subs.subscriptionId)
        if result.is_success:
            user_subs.status = result.subscription.status
            if old_display_status == self.model.UI_TRIAL:
                user_subs.display_status = self.model.UI_TRIAL_CANCELED
                # reset billingEndDate because it was set to billingStartDate + billingCycleMonths by createBtSubscription
                user_subs.billingEndDate = user_subs.billingStartDate
            elif old_display_status != self.model.UI_SUSPENDED:  # leave UI_SUSPENDED as is to preserve this info
                user_subs.display_status = self.model.UI_EXPIRED
            user_subs.save()
        return result


    def switchTrialToActive(self, user_subs, payment_token, new_plan=None):
        """User wants to upgrade to Active right now and their current status
        is either UI_TRIAL or UI_TRIAL_CANCELED.
        Args:
            user_subs: existing UserSubscription
            payment_token:str payment method token
            new_plan: SubscriptionPlan / None (if None, use existing plan)
        Cancel existing subs (if in TRIAL).
        Create new Active subscription with any signup discounts for which the user is eligible.
        Returns (Braintree result object, UserSubscription)
        """

        plan = new_plan if new_plan else user_subs.plan
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
        if user_subs.display_status == UserSubscription.UI_TRIAL:
            cancel_result = self.terminalCancelBtSubscription(user_subs)
            if not cancel_result.is_success:
                logger.warning('SwitchTrialToActive: Cancel old subscription failed for {0.subscriptionId} with message: {1.message}'.format(user_subs, cancel_result))
                return (cancel_result, user_subs)
        # Create new subscription. Returns (result, new_user_subs)
        return self.createBtSubscription(user, plan, subs_params)


    def updateSubscriptionFromBt(self, user_subs, bt_subs):
        """Update UserSubscription instance from braintree Subscription object
        and save the model instance.
        """
        billingAmount = user_subs.nextBillingAmount
        user_subs.status = bt_subs.status
        if bt_subs.status == self.model.ACTIVE:
            today = timezone.now()
            if (today < user_subs.billingFirstDate):
                user_subs.display_status = self.model.UI_TRIAL
            elif bt_subs.never_expires:
                user_subs.display_status = self.model.UI_ACTIVE
            else:
                if user_subs.display_status not in (self.model.UI_ACTIVE_CANCELED, self.model.UI_ACTIVE_DOWNGRADE):
                    logger.warning('Invalid display_status for subscriptionId: {0.subcriptionId}'.format(user_subs))
        elif bt_subs.status == self.model.PASTDUE:
            user_subs.display_status = self.model.UI_SUSPENDED
        elif bt_subs.status == self.model.CANCELED:
            if user_subs.display_status not in (self.model.UI_EXPIRED, self.model.UI_SUSPENDED, self.model.UI_TRIAL_CANCELED):
                logger.error('Invalid display_status for canceled subscriptionId: {0.subcriptionId}'.format(user_subs))
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

    def completeDowngrade(self, user_subs, payment_token):
        """This is called by a management cmd to complete the scheduled downgrade
        subscription requested by the user.
        It should be called when the billingCycle on the current subscription is
        about to end (because the user has already paid for the entire cycle).
        It terminates the current subs, and starts a new subscription using the plan
        specified in user_subs.next_plan. It also applies any earned discounts to the
        full price of the plan (override the first-year discount since it is no longer applicable).
        Args:
            user_subs: UserSubscription instance with status=UI_ACTIVE_DOWNGRADE and about to end.
            payment_token: Payment token to use for the new subscription.
        """
        new_plan = user_subs.next_plan
        if not new_plan:
            raise ValueError('completeDowngrade: next_plan not set on user subscription {0}'.format(user_subs))
        plan_discount = Discount.objects.get(discountType=new_plan.planId, activeForType=True)
        bt_subs = self.findBtSubscription(user_subs.subscriptionId)
        # get any earned discounts
        discount = Discount.objects.get(discountType=INVITER_DISCOUNT_TYPE, activeForType=True)
        # value will be used to override the default plan first-year discount
        discount_amount = 0 # default of 0 means: user will be charged full price (override first-year discount)
        for d in bt_subs.discounts:
            if d.id == discount.discountId:
                discount_amount = discount.amount*d.quantity
                break
        logger.debug('completeDowngrade discount amount: {0}'.format(discount_amount))
        # cancel old user_subs
        cancel_result = self.terminalCancelBtSubscription(user_subs)
        if not cancel_result.is_success:
            if cancel_result.message == self.model.RESULT_ALREADY_CANCELED:
                logger.info('completeDowngrade: existing bt_subs already canceled for: {0}'.format(user_subs))
                self.updateSubscriptionFromBt(user_subs, bt_subs)
            else:
                logger.warning('completeDowngrade: Cancel old subscription failed for {0.subscriptionId} with message: {1.message}'.format(user_subs, cancel_result))
                return (cancel_result, user_subs)
        # start new user_subs
        subs_params = {
            'plan_id': new_plan.planId,
            'trial_duration': 0,
            'payment_method_token': payment_token,
            'discounts': {
                'update': [
                    {
                        'existing_id': plan_discount.discountId,
                        'amount': discount_amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                    }
                ]
            }
        }
        result = braintree.Subscription.create(subs_params)
        if result.is_success:
            logger.info('completeDowngrade result: {0.is_success}'.format(result))
            new_user_subs = self.createSubscriptionFromBt(user, new_plan, result.subscription)
            return (result, new_user_subs)
        else:
            logger.warning('completeDowngrade result: {0.is_success}'.format(result))
            return (result, None)


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
    UI_ACTIVE_DOWNGRADE = 'Active-Downgrade-Scheduled'
    UI_TRIAL_CANCELED = 'Trial-Canceled'
    UI_SUSPENDED = 'Suspended'
    UI_EXPIRED = 'Expired'
    UI_STATUS_CHOICES = (
        (UI_TRIAL, UI_TRIAL),
        (UI_ACTIVE, UI_ACTIVE),
        (UI_ACTIVE_CANCELED, UI_ACTIVE_CANCELED),
        (UI_SUSPENDED, UI_SUSPENDED),
        (UI_EXPIRED, UI_EXPIRED),
        (UI_TRIAL_CANCELED, UI_TRIAL_CANCELED),
        (UI_ACTIVE_DOWNGRADE, UI_ACTIVE_DOWNGRADE),
    )
    RESULT_ALREADY_CANCELED = 'Subscription has already been canceled.'
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
    next_plan = models.ForeignKey(SubscriptionPlan,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
        blank=True,
        default=None,
        help_text='Used to store plan for pending downgrade'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = UserSubscriptionManager()

    def __str__(self):
        return self.subscriptionId

class SubscriptionEmailManager(models.Manager):
    def getOrCreate(self, user_subs):
        """Get or create model instance for (user_subs, user_subs.billingCycle)
        Returns tuple (model instance, created:bool)
        """
        return self.model.objects.get_or_create(
                subscription=user_subs,
                billingCycle=user_subs.billingCycle)


@python_2_unicode_compatible
class SubscriptionEmail(models.Model):
    """Used to keep track of reminder emails sent for renewal and other notices per billingCycle"""
    subscription = models.ForeignKey(UserSubscription,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='subscriptionemails',
    )
    billingCycle = models.PositiveIntegerField()
    remind_renew_sent = models.BooleanField(default=False, help_text='set to True upon sending of renewal reminder email')
    expire_alert_sent = models.BooleanField(default=False, help_text='set to True upon sending of card expiry alert email')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = SubscriptionEmailManager()

    class Meta:
        unique_together = ('subscription', 'billingCycle')

    def __str__(self):
        return '{0.subscription.subscriptionId}|{0.billingCycle}|{0.remind_renew_sent}'.format(self)


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
    tag = models.ForeignKey(CmeTag,
        on_delete=models.PROTECT,
        related_name='certificates',
        null=True,
        default=None,
        db_index=True
    )
    state_license = models.ForeignKey(StateLicense,
        on_delete=models.PROTECT,
        related_name='certificates',
        null=True,
        default=None,
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
    description = models.CharField(max_length=500, blank=True, default='')
    accept_query_keys = models.TextField(blank=True, default='', help_text='accepted keys in url query')
    has_paywall = models.BooleanField(blank=True, default=False, help_text='True if full text is behind paywall')
    allow_page_download = models.BooleanField(blank=True, default=True,
            help_text='False if pages under this host should not be downloaded')
    is_secure = models.BooleanField(blank=True, default=False, help_text='True if site uses a secure connection (https).')
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
    metadata = models.TextField(blank=True, default='')
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

# OrbitCmeOffer
# An offer for a user is generated based on the user's plugin activity.
@python_2_unicode_compatible
class OrbitCmeOffer(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='new_offers',
        db_index=True
    )
    sponsor = models.ForeignKey(Sponsor,
        on_delete=models.PROTECT,
        related_name='new_offers',
        db_index=True
    )
    eligible_site = models.ForeignKey(EligibleSite,
        on_delete=models.PROTECT,
        related_name='new_offers',
        db_index=True)
    url = models.ForeignKey(AllowedUrl,
        on_delete=models.PROTECT,
        related_name='new_offers',
        db_index=True)
    activityDate = models.DateTimeField()
    suggestedDescr = models.TextField(blank=True, default='')
    expireDate = models.DateTimeField()
    redeemed = models.BooleanField(default=False)
    valid = models.BooleanField(default=True)
    credits = models.DecimalField(max_digits=5, decimal_places=2,
        help_text='CME credits to be awarded upon redemption')
    tags = models.ManyToManyField(
        CmeTag,
        blank=True,
        related_name='new_offers',
        help_text='Suggested tags (intersected with user cmeTags by UI)'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'trackers_orbitcmeoffer'
        verbose_name_plural = 'OrbitCME Offers'

    def __str__(self):
        return self.url.url

    def activityDateLocalTz(self):
        return self.activityDate.astimezone(LOCAL_TZ)

    def formatSuggestedTags(self):
        return ", ".join([t.name for t in self.tags.all()])
    formatSuggestedTags.short_description = "suggestedTags"

    def assignCmeTags(self):
        """Assign tags based on: eligible_site, url, and user"""
        esite = self.eligible_site
        # get suggested cmetags from the eligible_site.specialties
        specnames = [p.name for p in esite.specialties.all()]
        spectags = CmeTag.objects.filter(name__in=specnames) # tags whose name=pracspec.name
        self.tags.set(list(spectags))
        # tags from allowed_url
        for t in self.url.cmeTags.all():
            self.tags.add(t)
        # check if can add SA-CME tag
        profile = self.user.profile
        if profile.isPhysician() and profile.specialties.filter(name__in=SACME_SPECIALTIES).exists():
            self.tags.add(CmeTag.objects.get(name=CMETAG_SACME))
