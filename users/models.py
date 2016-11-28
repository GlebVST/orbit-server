from __future__ import unicode_literals

import datetime
from decimal import Decimal
import uuid
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db import models
#from django.contrib.contenttypes.fields import GenericForeignKey
#from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

#
# constants (should match the database values)
#
ENTRYTYPE_REWARD = 'reward'
ENTRYTYPE_BRCME = 'browser-cme'
ENTRYTYPE_EXBRCME = 'expired-browser-cme'
ENTRYTYPE_SRCME = 'sr-cme'
CMETAG_SACME = 'SA-CME'

@python_2_unicode_compatible
class Degree(models.Model):
    """Names and abbreviations of professional degrees"""
    abbrev = models.CharField(max_length=5, unique=True)
    name = models.CharField(max_length=30)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.abbrev

@python_2_unicode_compatible
class PracticeSpecialty(models.Model):
    """Names of practice specialties.
    TODO: add OccupationType ForeignKey (Phase 2)
    """
    name = models.CharField(max_length=100, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    class Meta:
        verbose_name_plural = 'Practice Specialties'

# CME tag types (SA-CME, Breast, etc)
@python_2_unicode_compatible
class CmeTag(models.Model):
    name= models.CharField(max_length=20, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    class Meta:
        verbose_name_plural = 'CME Tags'


@python_2_unicode_compatible
class Profile(models.Model):
    user = models.OneToOneField(User,
        on_delete=models.CASCADE,
        primary_key=True
    )
    firstName = models.CharField(max_length=30)
    lastName = models.CharField(max_length=30)
    jobTitle = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True) # about me
    npiNumber = models.CharField(max_length=20, blank=True)
    inviteId = models.CharField(max_length=12, unique=True)
    socialUrl = models.URLField(blank=True)
    pictureUrl = models.URLField(max_length=300, blank=True)
    cmeTags = models.ManyToManyField(CmeTag, related_name='profiles')
    degrees = models.ManyToManyField(Degree)
    specialties = models.ManyToManyField(PracticeSpecialty)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '{0} {1}'.format(self.firstName, self.lastName)

@python_2_unicode_compatible
class Customer(models.Model):
    user = models.OneToOneField(User,
        on_delete=models.CASCADE,
        primary_key=True
    )
    customerId = models.UUIDField(unique=True, editable=False, default=uuid.uuid4,
        help_text='Used for Braintree customerId')
    contactEmail = models.EmailField(blank=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.customerId)

# Browser CME offer
# An offer for a user is generated based on the user's plugin activity.
@python_2_unicode_compatible
class BrowserCmeOffer(models.Model):
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        db_index=True
    )
    activityDate = models.DateTimeField()
    url = models.URLField(max_length=500)
    pageTitle = models.TextField(blank=True)
    expireDate = models.DateTimeField()
    redeemed = models.BooleanField(default=False)
    points = models.DecimalField(max_digits=6, decimal_places=2,
        help_text='Points needed to redeem this offer')
    credits = models.DecimalField(max_digits=5, decimal_places=2,
        help_text='CME credits to be awarded upon redemption')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.url
    class Meta:
        verbose_name_plural = 'BrowserCME Offers'

# Extensible list of entry types that can appear in a user's feed
@python_2_unicode_compatible
class EntryType(models.Model):
    name = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=100, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

# Base class for all feed entries (contains fields common to all entry types)
# A entry belongs to a user, and is defined by an activityDate and
# a description.
@python_2_unicode_compatible
class Entry(models.Model):
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        db_index=True
    )
    entryType = models.ForeignKey(EntryType,
        on_delete=models.PROTECT,
        db_index=True
    )
    activityDate = models.DateTimeField()
    description = models.CharField(max_length=500)
    valid = models.BooleanField(default=True)
    document = models.FileField(upload_to='entries', blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username
    class Meta:
        verbose_name_plural = 'Entries'

# Reward entry to show points earned by user
@python_2_unicode_compatible
class Reward(models.Model):
    entry = models.OneToOneField(Entry,
        on_delete=models.CASCADE,
        related_name='reward',
        primary_key=True
    )
    rewardType = models.CharField(max_length=30)
    points = models.DecimalField(max_digits=6, decimal_places=2)

    def __str__(self):
        return self.rewardType

# Self-reported CME
# Earned credits are self-reported along with the relevant cme tags
@python_2_unicode_compatible
class SRCme(models.Model):
    entry = models.OneToOneField(Entry,
        on_delete=models.CASCADE,
        related_name='srcme',
        primary_key=True
    )
    credits = models.DecimalField(max_digits=6, decimal_places=2)
    tags = models.ManyToManyField(CmeTag, related_name='srcmes')

    def __str__(self):
        return str(self.credits)


# Browser CME entry
# An entry is created when a Browser CME offer is redeemed by the user
# in exchange for points.
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

# Expired Browser CME entry
# An entry is created for an expired Browser CME offer that was never redeemed
@python_2_unicode_compatible
class ExBrowserCme(models.Model):
    entry = models.OneToOneField(Entry,
        on_delete=models.CASCADE,
        related_name='exbrcme',
        primary_key=True
    )
    offer = models.OneToOneField(BrowserCmeOffer,
        on_delete=models.PROTECT,
        related_name='exbrcme',
        db_index=True
    )
    url = models.URLField(max_length=500)
    pageTitle = models.TextField()

    def __str__(self):
        return self.url


# User points activity
# (+) User can purchase points (entry is null)
# (+) User can earn points (entry is Reward)
# (-) User has points deducted in order to redeem BrowserCmeOffer (entry is BrowserCme).
@python_2_unicode_compatible
class PointTransaction(models.Model):
    customer = models.ForeignKey(Customer,
        on_delete=models.CASCADE,
        db_index=True
    )
    entry = models.OneToOneField(Entry,
        null=True,
        on_delete=models.PROTECT
    )
    points = models.DecimalField(max_digits=6, decimal_places=2)
    pricePaid = models.DecimalField(max_digits=6, decimal_places=2)
    transactionId = models.CharField(max_length=36, unique=True)
    valid = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.transactionId

# Available options for purchasing points
@python_2_unicode_compatible
class PointPurchaseOption(models.Model):
    points = models.DecimalField(max_digits=6, decimal_places=2)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.points)

# Available options for earning points
@python_2_unicode_compatible
class PointRewardOption(models.Model):
    points = models.DecimalField(max_digits=6, decimal_places=2)
    rewardType = models.CharField(max_length=30, unique=True)
    description = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.rewardType

@python_2_unicode_compatible
class UserFeedback(models.Model):
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        db_index=True
    )
    message = models.CharField(max_length=500)
    hasBias = models.BooleanField(default=False)
    hasUnfairContent = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.message
    class Meta:
        verbose_name_plural = 'User Feedback'
