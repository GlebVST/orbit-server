from __future__ import unicode_literals
import braintree
from datetime import datetime
from decimal import Decimal
import pytz
import uuid
from dateutil.relativedelta import *
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Sum
#from django.contrib.contenttypes.fields import GenericForeignKey
#from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

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
class Degree(models.Model):
    """Names and abbreviations of professional degrees"""
    abbrev = models.CharField(max_length=7, unique=True)
    name = models.CharField(max_length=40)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.abbrev

# CME tag types (SA-CME, Breast, etc)
@python_2_unicode_compatible
class CmeTag(models.Model):
    name= models.CharField(max_length=20, unique=True)
    priority = models.IntegerField(
        default=0,
        help_text='Used for non-alphabetical sort.'
    )
    description = models.CharField(max_length=200, blank=True, help_text='Used for tooltip')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

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
    cmeTags = models.ManyToManyField(CmeTag,
        blank=True,
        related_name='specialties',
        help_text='Eligible cmeTags for this specialty'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

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
    inviteId = models.CharField(max_length=12, unique=True)
    socialId = models.CharField(max_length=64, blank=True, help_text='FB social auth ID')
    cmeTags = models.ManyToManyField(CmeTag, related_name='profiles', blank=True)
    degrees = models.ManyToManyField(Degree, blank=True) # TODO: switch to single ForeignKey
    specialties = models.ManyToManyField(PracticeSpecialty, blank=True)
    verified = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.lastName

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
        md = Degree.objects.get(abbrev=DEGREE_MD)
        do = Degree.objects.get(abbrev=DEGREE_DO)
        has_md = self.degrees.filter(pk=md.pk).exists()
        has_do = self.degrees.filter(pk=do.pk).exists()
        if has_md or has_do:
            return True
        return False


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


@python_2_unicode_compatible
class Customer(models.Model):
    user = models.OneToOneField(User,
        on_delete=models.CASCADE,
        primary_key=True
    )
    customerId = models.UUIDField(unique=True, editable=False, default=uuid.uuid4,
        help_text='Used for Braintree customerId')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = CustomerManager()

    def __str__(self):
        return str(self.customerId)

# Sponsors for entries in feed
@python_2_unicode_compatible
class Sponsor(models.Model):
    name = models.CharField(max_length=200, unique=True)
    url = models.URLField(max_length=1000, blank=True, help_text='Link to website of sponsor')
    logo_url = models.URLField(max_length=1000, help_text='Link to logo of sponsor')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

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
# A entry belongs to a user, and is defined by an activityDate and a description.
class EntryManager(models.Manager):

    def sumSRCme(self, user, startDate, endDate, tag=None):
        """
        Total Srcme credits over the given time period for
        the given user. Optional extra filter by cmetag.
        """
        filter_kwargs = dict(
            user=user,
            activityDate__gte=startDate,
            activityDate__lte=endDate
        )
        if tag:
            filter_kwargs['tags__exact'] = tag
        qset = self.model.objects.filter(**filter_kwargs)
        total = qset.aggregate(credit_sum=Sum('srcme__credits'))
        credit_sum = total['credit_sum']
        if credit_sum:
            return float(credit_sum)
        return 0

    def sumBrowserCme(self, user, startDate, endDate, tag=None):
        """
        Total BrowserCme credits over the given time period for
        the given user. Optional extra filter by cmetag.
        """
        filter_kwargs = dict(
            entry__user=user,
            entry__activityDate__gte=startDate,
            entry__activityDate__lte=endDate
        )
        if tag:
            filter_kwargs['entry__tags__exact'] = tag
        qset = BrowserCme.objects.select_related('entry').filter(**filter_kwargs)
        total = qset.aggregate(credit_sum=Sum('credits'))
        credit_sum = total['credit_sum']
        if credit_sum:
            return float(credit_sum)
        return 0


def entry_document_path(instance, filename):
    return '{0}/uid_{1}/{2}'.format(settings.FEED_MEDIA_BASEDIR, instance.user.id, filename)

@python_2_unicode_compatible
class Document(models.Model):
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
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
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.md5sum


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
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = EntryManager()

    def __str__(self):
        return '{0} on {1}'.format(self.entryType, self.activityDate)

    class Meta:
        verbose_name_plural = 'Entries'

# Notification entry (message to user in feed)
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

@python_2_unicode_compatible
class EligibleSite(models.Model):
    """Eligible (or white-listed) domains that will be recognized by the plugin.
    To start, we will have a manual system for translating data in this model
    into the AllowedUrl model.
    """
    domain_url = models.URLField(max_length=500,
        help_text='e.g. https://www.wikipedia.org/')
    domain_title = models.CharField(max_length=300, blank=True,
        help_text='e.g. Wikipedia Anatomy Pages')
    is_valid_domurl = models.BooleanField(default=True)
    example_url = models.URLField(max_length=1000,
        help_text='A URL within the given domain')
    example_title = models.CharField(max_length=300, blank=True,
        help_text='Label for the example URL')
    is_valid_expurl = models.BooleanField(default=True)
    description = models.CharField(max_length=500, blank=True)
    specialties = models.ManyToManyField(PracticeSpecialty, blank=True)
    needs_ad_block = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.domain_url


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
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.planId

# User Subscription
# https://articles.braintreepayments.com/guides/recurring-billing/subscriptions
class UserSubscriptionManager(models.Manager):
    def getLatestSubscription(self, user):
        qset = UserSubscription.objects.filter(user=user).order_by('-created')
        if qset.exists():
            return qset[0]

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
        and create user_subs object in local db
        Returns (Braintree result object, UserSubscription object)
        """
        user_subs = None
        result = braintree.Subscription.create(subs_params)
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
            firstDate = timezone.make_aware(result.subscription.first_billing_date, pytz.utc)
            startDate = result.subscription.billing_period_start_date
            if startDate:
                startDate = timezone.make_aware(startDate, pytz.utc)
            else:
                startDate = firstDate
            endDate = result.subscription.billing_period_end_date
            if endDate:
                endDate = timezone.make_aware(endDate, pytz.utc)
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
        return (result, user_subs)

    def makeActiveCanceled(self, user_subs):
        """
        Use case: User does not want to renew subscription,
        and their subscription is currently active and we have
        not reached billingEndDate.
        Model: set display_status to UI_ACTIVE_CANCELED.
        Bt: set number_of_billing_cycles on the subscription.
        Once this number is reached, the subscription will expire.
        Can raise braintree.exceptions.not_found_error.NotFoundError
        Returns Braintree result object
        """
        subscription = braintree.Subscription.find(user_subs.subscriptionId)
        # When subscription passes the billing_period_end_date, the current_billing_cycle is incremented
        curBillingCycle = subscription.current_billing_cycle
        if not curBillingCycle:
            curBillingCycle = 0
        # Set the max number of billing cycles. When this is reached, the subscription will expire in braintree.
        numBillingCycles = curBillingCycle + 1
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
        Update model: set display_status to UI_EXPIRED.
        Reference: https://developers.braintreepayments.com/reference/request/subscription/cancel/python
        Can raise braintree.exceptions.not_found_error.NotFoundError
        Returns Braintree result object
        """
        result = braintree.Subscription.cancel(user_subs.subscriptionId)
        if result.is_success:
            user_subs.status = result.subscription.status
            user_subs.display_status = self.model.UI_EXPIRED
            user_subs.save()
        return result


    def checkTrialToActive(self, user_subs):
        """
            Check if user_subs is out of trial period.
            Returns: bool if user_subs was saved with new data from bt subscription.
        """
        today = timezone.now()
        saved = False
        if user_subs.display_status == self.model.UI_TRIAL and (today > user_subs.billingFirstDate):
            subscription = braintree.Subscription.find(user_subs.subscriptionId)
            user_subs.status = subscription.status
            if subscription.status == self.model.ACTIVE:
                user_subs.display_status = self.model.UI_ACTIVE
            elif subscription.status == self.models.PASTDUE:
                user_subs.display_status = self.models.UI_SUSPENDED
            startDate = subscription.billing_period_start_date
            endDate = subscription.billing_period_end_date
            if startDate:
                startDate = timezone.make_aware(startDate, pytz.utc)
                if user_subs.billingStartDate != startDate:
                    user_subs.billingStartDate = startDate
            if endDate:
                endDate = timezone.make_aware(endDate, pytz.utc)
                if user_subs.billingEndDate != endDate:
                    user_subs.billingEndDate = endDate
            user_subs.billingCycle = subscription.current_billing_cycle
            user_subs.save()
            saved = True
        return saved

    def searchBtSubscriptionsByPlan(self, planId):
        """Search Braintree subscriptions by plan.
        https://developers.braintreepayments.com/reference/request/subscription/search/python
        https://developers.braintreepayments.com/reference/response/subscription/python
        Returns Braintree collection object (list of Subscription result objects)
        """
        collection = braintree.Subscription.search(braintree.SubscriptionSearch.plan_id == planId)
        for subs in collection.items:
            print('subscriptionId:{0} status:{1} start:{2} end:{3}.'.format(
                subs.subscriptionId,
                subs.status,
                subs.billing_period_start_date,
                subs.billing_period_end_date
            ))
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
    UI_SUSPENDED = 'Suspended'
    UI_EXPIRED = 'Expired'
    UI_STATUS_CHOICES = (
        (UI_TRIAL, UI_TRIAL),
        (UI_ACTIVE, UI_ACTIVE),
        (UI_ACTIVE_CANCELED, UI_ACTIVE_CANCELED),
        (UI_SUSPENDED, UI_SUSPENDED),
        (UI_EXPIRED, UI_EXPIRED)
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
    billingCycle = models.PositiveIntegerField(default=1, help_text='Braintree current_billing_cycle')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = UserSubscriptionManager()

    def __str__(self):
        return self.subscriptionId

