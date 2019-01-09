"""Payment and subscription-related models"""
from __future__ import unicode_literals
import logging
import braintree
import calendar
from datetime import datetime, timedelta
from dateutil.relativedelta import *
from decimal import Decimal, ROUND_HALF_UP
from hashids import Hashids
import pytz
import uuid
from django.conf import settings
from django.contrib.auth.models import User, Group, Permission
from django.core.exceptions import ValidationError
from django.db import models, connection
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from .base import (
    ACTIVE_OFFDATE,
    Organization,
    Degree,
    PracticeSpecialty
)
from .feed import BrowserCme
from common.appconstants import (
    GROUP_ENTERPRISE_MEMBER,
    GROUP_ENTERPRISE_ADMIN,
    ALL_PERMS,
    PERM_VIEW_FEED,
    PERM_VIEW_DASH,
    PERM_VIEW_GOAL,
    PERM_POST_BRCME,
    PERM_DELETE_BRCME,
    PERM_EDIT_BRCME,
    PERM_ALLOW_INVITE,
    PERM_EDIT_PROFILECMETAG
)

logger = logging.getLogger('gen.models')

#
# constants (should match the database values)
#
INVITER_DISCOUNT_TYPE = 'inviter'
INVITEE_DISCOUNT_TYPE = 'invitee'
CONVERTEE_DISCOUNT_TYPE = 'convertee'
ORG_DISCOUNT_TYPE = 'org'
BASE_DISCOUNT_TYPE = 'base'

TWO_PLACES = Decimal('.01')

def makeAwareDatetime(a_date, tzinfo=pytz.utc):
    """Convert <date> to <datetime> with timezone info"""
    return timezone.make_aware(
        datetime.combine(a_date, datetime.min.time()), tzinfo)

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

    def formatCard(self, payment_method):
        """Create card info used for emails
        Args:
            payment_method: dict from getPaymentMethods
        Returns: dict {
            card_type:str
            last4:str
            expiry:str as mm/yyyy
            expiration_date:datetime
        """
        return {
            'type': payment_method['type'],
            'last4': payment_method['number'][-4:],
            'expiry': payment_method['expiry'],
            'expiration_date': self.getDateFromExpiry(payment_method['expiry'])
        }

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
        return end_dt

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
        """Returns SignupDiscount instance/None for the given user
        If user joined before a specific cutoff date, and their email domain matches an existing row, then return the matching SignupDiscount instance, else None.
        """
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
    expireDate = models.DateTimeField(help_text='Cutoff for user signup date [UTC]')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = SignupDiscountManager()

    class Meta:
        unique_together = ('email_domain', 'discount', 'expireDate')

    def __str__(self):
        return '{0.organization}|{0.email_domain}|{0.discount.discountId}|{0.expireDate}'.format(self)


class SignupEmailPromoManager(models.Manager):

    def get_casei(self, email):
        """Search by email.lower() and return model Instance or None if none exists"""
        lc_email = email.lower()
        if self.model.objects.filter(email=lc_email).exists():
            return self.model.objects.get(email=lc_email)
        return None

@python_2_unicode_compatible
class SignupEmailPromo(models.Model):
    email = models.EmailField(unique=True)
    first_year_price = models.DecimalField(max_digits=5, decimal_places=2, help_text='First year promotional price')
    display_label = models.CharField(max_length=60, blank=True, default='',
            help_text='Display label shown to the user in the discount screen')
    created = models.DateTimeField(auto_now_add=True)
    objects = SignupEmailPromoManager()

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
    # maximum number of invites for which a discount is applied to the inviter's subscription.
    INVITER_MAX_NUM_DISCOUNT = 10
    # fields
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
        blank=True,
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
                if user_subs and user_subs.status == UserSubscription.ACTIVE and user_subs.transactions.exists():
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
    use_free_plan = models.BooleanField(default=False,
            help_text='If true: expects a Free Plan assigned to it, to be used in place of the BT Plan for signup')
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

class SubscriptionPlanType(models.Model):
    BRAINTREE = 'Braintree'
    FREE_INDIVIDUAL = 'Free'
    ENTERPRISE = 'Enterprise'
    # fields
    name = models.CharField(max_length=64, unique=True,
            help_text='Name of plan type. Must be unique.')
    needs_payment_method = models.BooleanField(default=False,
            help_text='If true: requires payment method on signup to create a UserSubscription.')
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

    def getPlansForKey(self, plan_key):
        """This swaps out the Braintree Plan for the Free Plan depending on plan_key.use_free_plan.
        Args:
            plan_key: SubscriptionPlanKey instance
        If plan_key.use_free_plan is True:
            The BT Basic Plan is swapped out for the Free Basic Plan.
            return [
                Free Basic Plan,  # no payment method at signup
                BT Pro Plan         # needs payment method at signup
            ]
        else:
            Only Braintree-type plans are returned. These require a payment method at signup
            return [
                BT Basic Plan,
                BT Pro Plan
            ]
        Note: Pro plan is unaffected by plan_key and is always the Braintree plan.
        Returns: SubscriptionPlan queryset order by price
        """
        pt_bt = SubscriptionPlanType.objects.get(name=SubscriptionPlanType.BRAINTREE)
        pt_free = SubscriptionPlanType.objects.get(name=SubscriptionPlanType.FREE_INDIVIDUAL)
        filter_kwargs = dict(active=True, plan_key=plan_key)
        if plan_key.use_free_plan:
            qset = self.model.objects.filter(
                Q(plan_type=pt_free, display_name='Basic') | Q(plan_type=pt_bt, display_name='Pro'),
                **filter_kwargs
            )
        else:
            filter_kwargs['plan_type'] = pt_bt
            qset = self.model.objects.filter(**filter_kwargs)
        return qset.order_by('price')

    def getPaidPlanForFreePlan(self, free_plan):
        """Return upgrade_plan for the given free plan
        Args:
            free_plan: SubscriptionPlan whose plan_type is free-individual
        Returns: SubscriptionPlan/None
        """
        return free_plan.upgrade_plan

    def getEnterprisePlanForOrg(self, org):
        """This returns SubscriptionPlan assigned to the given org
        Raises IndexError if none found
        """
        qset = self.model.objects.select_related('plan_type').filter(
                organization=org,
                plan_type__name=SubscriptionPlanType.ENTERPRISE, active=True)
        return qset[0]

    def findPlanKeyForProfile(self, profile):
        """Find a plan_key that matches profile.degrees and specialties
        Args:
            profile: Profile instance
        Returns: SubscriptionPlanKey instance/None
        """
        # find pick first plan_key that matches user degree and specialty
        degree = profile.degrees.all()[0] if profile.degrees.exists() else None
        specs = [ps.pk for ps in profile.specialties.all()]
        filter_kwargs = dict()
        if degree:
            filter_kwargs['degree'] = degree
        if specs:
            filter_kwargs['specialty__in'] = specs
        if filter_kwargs:
            qset = SubscriptionPlanKey.objects.filter(**filter_kwargs).order_by('id')
            if qset.exists():
                return qset[0]
        return None

# All plans with plan_type=Braintree must be created in the Braintree Control Panel, and synced with the db.
# https://developers.braintreepayments.com/guides/recurring-billing/plans
@python_2_unicode_compatible
class SubscriptionPlan(models.Model):
    planId = models.CharField(max_length=36,
            unique=True,
            help_text='Unique. No whitespace. If plan_type is Braintree, the planId must be in sync with the actual plan in Braintree')
    name = models.CharField(max_length=80,
            help_text='Internal Plan name (alphanumeric only). If plan_type is Braintree, it must match value in Braintree. Will be used to set planId.')
    display_name = models.CharField(max_length=40,
            help_text='Display name - what the user sees (e.g. Standard).')
    price = models.DecimalField(max_digits=6, decimal_places=2, help_text=' in USD')
    trialDays = models.IntegerField(default=0,
            help_text='Trial period in days')
    billingCycleMonths = models.IntegerField(default=12,
            help_text='Billing Cycle in months')
    discountPrice = models.DecimalField(max_digits=6, decimal_places=2,
            help_text='discounted price in USD')
    active = models.BooleanField(default=True)
    plan_type = models.ForeignKey(SubscriptionPlanType,
        on_delete=models.PROTECT,
        db_index=True,
        related_name='plans',
    )
    plan_key = models.ForeignKey(SubscriptionPlanKey,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_index=True,
        related_name='plans',
        help_text='Used to group Individual plans for the pricing pages'
    )
    organization = models.ForeignKey(Organization,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
        blank=True,
        related_name='plans',
        help_text='Used to assign an enterprise plan to a particular Organization'
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
    # decided to keep the name of this field as maxCmeYear despite the fact it now holds a semantics of maxCmePeriod -
    # to keep things backwards compartible and avoid unnecessary production update risks
    maxCmeYear = models.PositiveIntegerField(
        default=0,
        help_text='Maximum allowed CME per plan period (defined via billingCycleMonths - can be one or multiple years). 0 for unlimited total.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = SubscriptionPlanManager()

    def __str__(self):
        return self.name

    def monthlyPrice(self):
        """returns formatted str"""
        return "{0:.2f}".format(self.price/self.billingCycleMonths)

    def discountMonthlyPrice(self):
        """returns formatted str"""
        return "{0:.2f}".format(self.discountPrice/self.billingCycleMonths)

    def isUnlimitedCme(self):
        """True if this is an un-limited plan, else False"""
        return self.maxCmeMonth == 0 and self.maxCmeYear == 0

    def isLimitedCmeRate(self):
        """True if this is an limited CME rate plan, else False"""
        return self.maxCmeMonth > 0

    def isEnterprise(self):
        return self.plan_type.name == SubscriptionPlanType.ENTERPRISE

    def isFreeIndividual(self):
        return self.plan_type.name == SubscriptionPlanType.FREE_INDIVIDUAL

    def isPaid(self):
        return self.plan_type.needs_payment_method


# User Subscription
# https://articles.braintreepayments.com/guides/recurring-billing/subscriptions
class UserSubscriptionManager(models.Manager):
    def getLatestSubscription(self, user):
        qset = UserSubscription.objects.select_related('plan').filter(user=user).order_by('-created')
        if qset.exists():
            return qset[0]

    def allowSignupDiscount(self, user):
        """Check if user is allowed signup discounts
        Args:
            user: User instance
        Returns: bool
        """
        # has user ever had a paid subs
        qset = UserSubscription.objects.select_related('plan').filter(user=user).order_by('created')
        for m in qset:
            if m.plan.isPaid():
                return False
        return True

    def setUserCmeCreditByPlan(self, user, plan):
        """Create or update UserCmeCredit instance for the given user.
        If instance already exists: update it to match plan's yearly limit, else create.
        This should be called when new user account is created, or when user's subscription plan changes.
        """
        plan_credits = plan.maxCmeYear
        if plan.isUnlimitedCme():
            plan_credits = self.model.MAX_FREE_SUBSCRIPTION_CME
        try:
            existingUserCredit = UserCmeCredit.objects.get(user=user)
        except UserCmeCredit.DoesNotExist:
            UserCmeCredit.objects.create(
                user=user,
                plan_credits=plan.maxCmeYear,
                boost_credits=0
            )
        else:
            existingUserCredit.plan_credits = plan_credits
            existingUserCredit.save()

    def refreshUserCmeCreditByCurrentPlan(self, user):
        subscription = self.getLatestSubscription(user=user)
        self.setUserCmeCreditByPlan(user, subscription.plan)

    def getPermissions(self, user_subs):
        """Helper method used by serialize_permissions.
        Get the permissions for the group that matches user_subs.display_status
        This does not handle extra permissions based on the user's assigned groups.
        Based on user_subs.plan:
            Include PERM_DELETE_BRCME for plans with isUnlimitedCme (no year or month limit)
            Include PERM_ALLOW_INVITE for paid plans with active status.
        Returns: Permission queryset
        """
        is_brcme_month_limit = False
        plan = user_subs.plan
        g = Group.objects.get(name=user_subs.display_status)
        qset = g.permissions.all()
        if plan.isUnlimitedCme():
            qset = qset.union(Permission.objects.filter(codename=PERM_DELETE_BRCME))
        else:
            now = timezone.now()
            if plan.isLimitedCmeRate():
                is_brcme_month_limit = BrowserCme.objects.hasEarnedMonthLimit(user_subs, now.year, now.month)
        if plan.isPaid() and user_subs.display_status == self.model.UI_ACTIVE:
            # UI will display unique invite url for this user to invite others
            qset = qset.union(Permission.objects.filter(codename=PERM_ALLOW_INVITE))
        qset = qset.order_by('codename')
        return (qset, is_brcme_month_limit)


    def serialize_permissions(self, user, user_subs):
        """This is used by auth_views and payment_views to return
        the allowed permissions for the user in the response.
        Returns list of dicts: [{codename:str, allowed:bool}]
        for the permissions in appconstants.ALL_PERMS.
        Exclude PERM_POST_BRCME if user depleted all cme credits.
        Returns:dict {
            permissions:list of dicts {codename, allow:bool},
            credits: {}
        }
        """
        allowed_codes = []
        is_brcme_month_limit = False
        is_unlimited_cme = False
        remaining_credits = 0
        plan_credits = 0
        boost_credits = 0
        # get any special groups to which the user belongs
        discard_codes = set([])
        group_names = set([])
        for g in user.groups.all():
            allowed_codes.extend([p.codename for p in g.permissions.all()])
            group_names.add(g.name)
            if g.name == GROUP_ENTERPRISE_MEMBER:
                discard_codes.add(PERM_EDIT_PROFILECMETAG)

        # remove standard ACTIVE user permissions like view_feed, view_dashboard etc. for pure enterprise admins
        if (GROUP_ENTERPRISE_ADMIN in group_names) and (GROUP_ENTERPRISE_MEMBER not in group_names):
            discard_codes.add(PERM_VIEW_FEED)
            discard_codes.add(PERM_VIEW_DASH)
            discard_codes.add(PERM_VIEW_GOAL)
        userCredits = None
        try:
            userCredits = UserCmeCredit.objects.get(user=user)
        except UserCmeCredit.DoesNotExist:
            # might be a case when user hasn't completed signup so don't have a subscription yet
            logger.debug('UserCmeCredit instance does not exist for user {0}'.format(user))
        else:
            remaining_credits = userCredits.remaining()
            plan_credits = userCredits.plan_credits
            boost_credits = userCredits.boost_credits
        if user_subs:
            qset, is_brcme_month_limit = self.getPermissions(user_subs) # Permission queryset
            allowed_codes.extend([p.codename for p in qset])
            if remaining_credits <= 0 or is_brcme_month_limit:
                # if reached cme credit limit or at monthly speed limit, disallow post of brcme (e.g. disallow redeem offer)
                discard_codes.add(PERM_POST_BRCME)
            if user_subs.plan:
                is_unlimited_cme = user_subs.plan.isUnlimitedCme()
                # allow referral banner only to users redeemed at least 10 Browser CME credits
                if userCredits and not is_unlimited_cme and (user_subs.plan.maxCmeYear - userCredits.plan_credits < 10):
                    discard_codes.add(PERM_ALLOW_INVITE)

        allowed_codes = set(allowed_codes)
        for codename in discard_codes:
            allowed_codes.discard(codename) # remove from set if exist
        perms = [{
                'codename': codename,
                'allow': codename in allowed_codes
            } for codename in ALL_PERMS]
        data = {
            'permissions': perms,
            'credits' : {
                'monthly_limit': is_brcme_month_limit,
                'unlimited': is_unlimited_cme,
                'plan_credits': plan_credits,
                'boost_credits': boost_credits
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
            bt_subs = braintree.Subscription.find(subscriptionId)
        except braintree.exceptions.not_found_error.NotFoundError:
            return None
        else:
            return bt_subs


    def createEnterpriseMemberSubscription(self, user, plan, startDate=None):
        """Create enterprise UserSubscription instance for the given user.
        Add user to GROUP_ENTERPRISE_MEMBER group.
        The display_status of the new subs is UI_ACTIVE.
        Note: The billing dates are not used for actual billing, but the
          start/end dates are advanced every cycle by checkEnterpriseSubs mgmt cmd.
        Args:
            user: User instance
            plan: SubscriptionPlan instance whose plan_type is ENTERPRISE
        Returns UserSubscription instance
        """
        if not startDate:
            startDate = user.date_joined
        endDate = startDate + relativedelta(months=plan.billingCycleMonths)
        now = timezone.now()
        nowId = now.strftime('%Y%m%d%H%M')
        subsId = "ent.{0}.{1}".format(user.pk, nowId) # a unique id
        user_subs = UserSubscription.objects.create(
            user=user,
            plan=plan,
            subscriptionId=subsId,
            display_status=UserSubscription.UI_ACTIVE,
            status=UserSubscription.ACTIVE,
            billingFirstDate=startDate,
            billingStartDate=startDate,
            billingEndDate=endDate,
            billingCycle=1
        )
        self.setUserCmeCreditByPlan(user, plan)
        user.groups.add(Group.objects.get(name=GROUP_ENTERPRISE_MEMBER))
        return user_subs

    def activateEnterpriseSubscription(self, user, org, plan):
        """Terminate current user_subs (if not Enterprise) and start new Enterprise member subscription.
        Set profile.organization to the given org
        Args:
            user: User instance
            org: Organization instance
            plan: SubscriptionPlan instance whose plan_type is ENTERPRISE
        Returns: UserSubscription instance
        """
        user_subs = self.getLatestSubscription(user)
        profile = user.profile
        now = timezone.now()
        if user_subs and not user_subs.inTerminalState():
            # terminate
            if user_subs.plan.isPaid():
                cancel_result = self.terminalCancelBtSubscription(user_subs)
                if cancel_result.is_success:
                    logger.info('activateEnterpriseSubscription: terminalCancelBtSubscription completed for {0.subscriptionId}'.format(user_subs))
                else:
                    logger.error('activateEnterpriseSubscription: terminalCancelBtSubscription failed for {0.subscriptionId}'.format(user_subs))
            else:
                if user_subs.plan.isEnterprise():
                    user_subs.display_status = UserSubscription.UI_ENTERPRISE_CANCELED
                else:
                    user_subs.display_status = UserSubscription.UI_TRIAL_CANCELED
                user_subs.status = UserSubscription.CANCELED
                user_subs.billingEndDate = now
                user_subs.save()
        # start new enterprise subs
        user_subs = self.createEnterpriseMemberSubscription(user, plan, now)
        # update profile
        profile.organization = org
        profile.planId = plan.planId
        profile.save(update_fields=('organization','planId'))
        return user_subs

    def createFreeSubscription(self, user, plan):
        """Create free-individual UserSubscription instance for the given plan.
        The display_status of the new subs is UI_TRIAL.
        The date fields are not billing dates, they only represent the duration of the free trial period.
        Args:
            user: User instance
            plan: SubscriptionPlan instance that is free
        Returns UserSubscription instance
        """
        startDate = timezone.now()
        endDate = startDate + timedelta(days=plan.trialDays)
        nowId = startDate.strftime('%Y%m%d%H%M')
        subsId = "fr.{0}.{1}".format(user.pk, nowId) # a unique id
        user_subs = UserSubscription.objects.create(
            user=user,
            plan=plan,
            subscriptionId=subsId,
            display_status=UserSubscription.UI_TRIAL,
            status=UserSubscription.ACTIVE,
            billingFirstDate=startDate,
            billingStartDate=startDate,
            billingEndDate=endDate
        )
        self.setUserCmeCreditByPlan(user, plan)
        return user_subs

    def endEnterpriseSubscription(self, user):
        """End the current Enterprise user_subs.
        Args:
            user: User instance
        Remove user from GROUP_ENTERPRISE_MEMBER group.
        Set profile.organization to None
        Find the appropriate Free Basic Plan for this user based on profile.
        Create Free user_subs and set to ENTERPRISE_CANCELED state. This allow user to use UI
        to enter in their payment info and activate a paid plan within the plan_key.
        """
        user_subs = self.getLatestSubscription(user)
        if not user_subs.plan.isEnterprise():
            logger.error('endEnterpriseSubscription: invalid subscription {0.subscriptionId}'.format(user_subs))
            return None
        profile = user.profile
        pt_free = SubscriptionPlanType.objects.get(name=SubscriptionPlanType.FREE_INDIVIDUAL)
        now = timezone.now()
        # end current user_subs
        user_subs.status = self.model.CANCELED
        user_subs.display_status = self.model.UI_EXPIRED
        user_subs.billingEndDate = now
        user_subs.save()
        # remove user from EnterpriseMember group
        ge = Group.objects.get(name=GROUP_ENTERPRISE_MEMBER)
        user.groups.remove(ge)
        # clear profile.organization
        profile.organization = None
        profile.save(update_fields=('organization',))
        # find appropriate plan_key for user
        plan_key = SubscriptionPlan.objects.findPlanKeyForProfile(profile)
        if not plan_key:
            logger.warning('endEnterpriseSubscription: could not find plan_key for user {0}. Remove enterprise user_subs.'.format(user))
            # delete enterprise user_subs so that user can join as individual user (or be re-added back to org)
            user_subs.delete()
            return
        # Assign user to the FREE_INDIVIDUAL Basic plan under plan_key
        filter_kwargs = dict(
                active=True,
                plan_key=plan_key,
                plan_type=pt_free,
                display_name='Basic'
                )
        qset = SubscriptionPlan.objects.filter(**filter_kwargs)
        if not qset.exists():
            logger.warning('endEnterpriseSubscription: no Free plan for plan_key: {0}'.format(plan_key))
            return
        # else
        free_plan = qset[0]
        f_user_subs = self.createFreeSubscription(user, free_plan)
        f_user_subs.status = self.model.CANCELED
        # this status directs UI to display a specific banner message to user
        f_user_subs.display_status = self.model.UI_ENTERPRISE_CANCELED
        f_user_subs.billingEndDate = now
        f_user_subs.save()
        # update available credit amount to conform with a new plan
        self.setUserCmeCreditByPlan(user, free_plan)
        profile.planId = free_plan.planId
        profile.save(update_fields=('planId',))
        logger.info('endEnterpriseSubscription: transfer user {0} to plan {1.name}'.format(user, free_plan))

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
        self.setUserCmeCreditByPlan(user, plan)
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
        subs_price = plan.discountPrice
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
            if is_convertee:
                affl = Affiliate.objects.get(user=inviter) # used below in saving AffiliatePayout instance
            # used below in saving InvitationDiscount/AffiliatePayout model instance
            inv_discount = Discount.objects.get(discountType=INVITEE_DISCOUNT_TYPE, activeForType=True)
        allow_signup = UserSubscription.objects.allowSignupDiscount(user)
        if allow_signup:
            # If user's email exists in SignupEmailPromo then it overrides any other discounts
            promo = SignupEmailPromo.objects.get_casei(user.email)
            if promo:
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
                # no promo, check other signup discounts
                if is_invitee or is_convertee:
                    discounts.append(inv_discount)
                    subs_price -= inv_discount.amount # update subs_price
                sd = SignupDiscount.objects.getForUser(user)
                if sd:
                    discount = sd.discount
                    discounts.append(discount)
                    logger.info('Signup discount: {0} for user {1}'.format(discount, user))
                    subs_price -= discount.amount # signup discount stacks on top of any inv_discount
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
            try:
                if is_invitee and not InvitationDiscount.objects.filter(invitee=user).exists():
                    # user can end/create subscription multiple times, but only add invitee once to InvitationDiscount.
                    InvitationDiscount.objects.create(
                        inviter=inviter,
                        invitee=user,
                        inviteeDiscount=inv_discount
                    )
                elif is_convertee and affl.bonus > 0 and not AffiliatePayout.objects.filter(convertee=user).exists():
                    afp_amount = affl.bonus*subs_price
                    AffiliatePayout.objects.create(
                        convertee=user,
                        converteeDiscount=inv_discount,
                        affiliate=affl, # Affiliate instance
                        amount=afp_amount
                    )
            except Exception, e:
                # catch all and return user_subs since we need the db transaction to commit since bt_subs was successfully created
                logger.error("createBtSubscription Exception after bt_subs was created: {0}".format(e))
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


    def getDiscountAmountForUpgrade(self, user_subs, new_plan, billingDay, numDaysInYear):
        """This should be called before current user_subs is canceled.
        It calculates the discount amount based on how much the user paid for their current
        annual subscription and how many days are left in the old subscription.
        Args:
            user_subs: UserSubscription
            new_plan: new (higher-priced) Plan
            billingDay: int 1-365 or 366.  day in the current billing cycle on the old plan
            numDaysInYear:int either 365 or 366
        Returns: (owed:Decimal, discount_amount:Decimal)
        """
        old_plan = user_subs.plan
        daysLeft = Decimal(numDaysInYear) - billingDay # days left in the old billing cycle
        cf = Decimal(numDaysInYear*1.0) # conversion factor to get daily plan price
        # find the amount user paid for current user_subs
        qset = user_subs.transactions.filter(
                status=SubscriptionTransaction.SETTLED,
                trans_type=SubscriptionTransaction.TYPE_SALE).order_by('-created')
        if qset.exists():
            amountPaid = qset[0].amount
        else:
            logger.warning('getDiscountAmountForUpgrade: could not find amount paid for user_subs {0.pk}'.format(user_subs))
            amountPaid = old_plan.price
        pricePerDay = amountPaid/cf
        discountAmount = pricePerDay*daysLeft
        # check user_subs.nextBillingAmount for extra earned discounts (e.g. from InvitationDiscount)
        if (user_subs.display_status == UserSubscription.UI_ACTIVE) and (old_plan.price > user_subs.nextBillingAmount):
            # user had earned some discounts that would have been applied to the next billing cycle on their old plan
            # (Active-Canceled users forfeited any earned discounts because they don't have a nextBillingAmount)
            extraDiscount = old_plan.price - user_subs.nextBillingAmount
            discountAmount += extraDiscount
        if discountAmount < 1:
            discountAmount = Decimal(0)
        # user will start brand new subscription on new plan with billingCycle back at 1
        owed = new_plan.discountPrice
        if owed > discountAmount:
            owed -= discountAmount
        else:
            owed = Decimal(0)
        return (owed, discountAmount)


    def upgradePlan(self, user_subs, new_plan, payment_token):
        """This is called to upgrade the user to a higher-priced plan (e.g. Basic to Pro).
        Cancel existing subscription, and create new one.
        If the old subscription had some discounts to be applied at the next cycle, and the discount total is less
        that is what is owed for upgrade, then apply these discounts to the new subscription.
        Returns (Braintree result object, UserSubscription)
        """
        old_plan = user_subs.plan
        logger.info('Upgrading from {0.planId} {0.name} ({0.plan_type.name}) to {1.planId} {1.name} ({1.plan_type.name})'.format(old_plan, new_plan))
        # check if a Free Trial subs then skip BT lookup
        if not old_plan.isFreeIndividual() and not settings.ENV_TYPE == settings.ENV_PROD:
            # In test env, we deliberately make db different from bt (e.g. to test suspended accounts)
            bt_subs = self.findBtSubscription(user_subs.subscriptionId)
            if not bt_subs:
                raise ValueError('upgradePlan BT subscription not found for subscriptionId: {0.subscriptionId}'.format(user_subs))
            self.updateSubscriptionFromBt(user_subs, bt_subs)
        user = user_subs.user
        if user_subs.display_status in (UserSubscription.UI_TRIAL, UserSubscription.UI_TRIAL_CANCELED):
            return self.switchTrialToActive(user_subs, payment_token, new_plan)
        # Get base-discount (must exist in Braintree)
        baseDiscount = Discount.objects.get(discountType=BASE_DISCOUNT_TYPE, activeForType=True)
        discountAmount = 0
        now = timezone.now()
        if user_subs.status == UserSubscription.EXPIRED:
            # user_subs is already in a terminal state
            discountAmount = 0
        elif user_subs.status == UserSubscription.CANCELED:
            # This method expects the user_subs to be canceled already
            if user_subs.display_status == UserSubscription.UI_TRIAL_CANCELED:
                # user can still get signup discounts
                discounts = UserSubscription.objects.getDiscountsForNewSubscription(user)
                for d in discounts:
                    discountAmount += d['discount'].amount
                logger.debug('discount: {0}'.format(discountAmount))
            else:
                discountAmount = 0
        else:
            # user has an active bt subscription that must be canceled
            # Calculate discountAmount based on daysLeft in user_subs
            td = now - user_subs.billingStartDate
            billingDay = Decimal(td.days)
            if billingDay == 0:
                billingDay = 1
            numDaysInYear = 365 if not calendar.isleap(now.year) else 366
            owed, discountAmount = self.getDiscountAmountForUpgrade(user_subs, new_plan, billingDay, numDaysInYear)
            logger.info('upgradePlan old_subs:{0.subscriptionId}|billingCycle={0.billingCycle}|billingDay={1}|discount={2}|owed={3}.'.format(
                user_subs,
                billingDay,
                discountAmount,
                owed
            ))
            # cancel existing subscription
            cancel_result = self.terminalCancelBtSubscription(user_subs)
            if not cancel_result.is_success:
                logger.warning('upgradePlan: Cancel old subscription failed for {0.subscriptionId} with message: {1.message}'.format(user_subs, cancel_result))
                return (cancel_result, user_subs)
        # Create new subscription
        subs_params = {
            'plan_id': new_plan.planId,
            'trial_duration': 0,
            'payment_method_token': payment_token
        }
        if discountAmount > 0:
            # Add discounts:add key to subs_params
            subs_params['discounts'] = {
                'add': [
                    {
                        "inherited_from_id": baseDiscount.discountId,
                        'amount': discountAmount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                    }
                ]
            }
        # create new bt subs
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


    def makeActiveDowngrade(self, downgrade_plan, user_subs):
        """
        Use case: User is currently in Pro, and wants to downgrade at end of current billing cycle.
        Update BT subscription and set never_expires=False and number_of_billing_cycles to current cycle.
        Update model instance: set display_status = UI_ACTIVE_DOWNGRADE
        Need separate management task that creates new subscription at end of the billing cycle.
        Returns Braintree result object
        """
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
            # cleanup next plan
            user_subs.next_plan = None
            if curBillingCycle:
                user_subs.billingCycle = curBillingCycle
            user_subs.save()
        return result


    def terminalCancelBtSubscription(self, user_subs):
        """
        Cancel Braintree subscription - this is a terminal state. Once
            canceled, a subscription cannot be reactivated.
        Update instance:
         1. set display_status to:
            UI_TRIAL_CANCELED if previous display_status was UI_TRIAL, else to UI_EXPIRED.
         2. Set billingEndDate to now. This stores when the subs was cancelled.
        Reference: https://developers.braintreepayments.com/reference/request/subscription/cancel/python
        Can raise braintree.exceptions.not_found_error.NotFoundError
        Returns Braintree result object
        """
        old_display_status = user_subs.display_status
        result = braintree.Subscription.cancel(user_subs.subscriptionId)
        if result.is_success:
            now = timezone.now()
            user_subs.status = result.subscription.status
            if old_display_status == self.model.UI_TRIAL:
                user_subs.display_status = self.model.UI_TRIAL_CANCELED
                # reset billingEndDate because it was set to billingStartDate + billingCycleMonths by createBtSubscription
                user_subs.billingEndDate = user_subs.billingStartDate
            elif old_display_status != self.model.UI_SUSPENDED:  # leave UI_SUSPENDED as is to preserve this info
                user_subs.display_status = self.model.UI_EXPIRED
            user_subs.billingEndDate = now
            user_subs.save()
        return result


    def switchTrialToActive(self, user_subs, payment_token, new_plan=None):
        """
        Args:
            user_subs: existing UserSubscription
            payment_token:str payment method token
            new_plan: SubscriptionPlan / None (if None, use existing plan)
        Returns: (Braintree result object, UserSubscription)
        If current subscription is a paid plan in Trial status:
            User wants to start billing right now, and their current status is either UI_TRIAL or UI_TRIAL_CANCELED.
            Steps:
                Cancel existing subscription if display_status is UI_TRIAL.
                Create new Active subscription with any signup discounts for which the user is eligible.
        else:
            Call startActivePaidPlan. Arg new_plan must be a paid SubscriptionPlan
        """
        cur_plan = user_subs.plan
        if cur_plan.isFreeIndividual():
            return self.startActivePaidPlan(user_subs, payment_token, new_plan)

        # If not given: new_plan is cur_plan
        # If given (e.g. by UpgradePlan): switch to new_plan
        plan = new_plan if new_plan else cur_plan
        user = user_subs.user
        profile = user.profile
        subs_params = {
            'plan_id': plan.planId,
            'trial_duration': 0,
            'payment_method_token': payment_token
        }
        if profile.inviter:
            qset = UserSubscription.objects.filter(user=user).exclude(pk=user_subs.pk)
            if not qset.exists():
                # User has no other subscription except this Trial which is to be canceled.
                # Can apply invitee discount to the new Active subscription
                if profile.affiliateId and Affiliate.objects.filter(user=user.profile.inviter).exists():
                    # inviter is Affiliate *and* profile.affiliateId is set which means user was converted
                    subs_params['convertee_discount'] = True
                    logger.info('SwitchTrialToActive: apply convertee discount to new subscription for {0}'.format(user))
                else:
                    subs_params['invitee_discount'] = True
                    logger.info('SwitchTrialToActive: apply invitee discount to new subscription for {0}'.format(user))
        if user_subs.display_status == UserSubscription.UI_TRIAL: # omit UI_TRIAL_CANCELED since it is already canceled
            cancel_result = self.terminalCancelBtSubscription(user_subs)
            if not cancel_result.is_success:
                logger.warning('SwitchTrialToActive: Cancel old subscription failed for {0.subscriptionId} with message: {1.message}'.format(user_subs, cancel_result))
                return (cancel_result, user_subs)
        # Create new subscription. Returns (result, new_user_subs)
        return self.createBtSubscription(user, plan, subs_params)


    def startActivePaidPlan(self, user_subs, payment_token, new_plan):
        """Switch user from their current free plan to their first active paid plan. This is called either by the ActivatePaidSubscription view (via the ActivatePaidUserSubsSerializer) or by switchTrialToActive manager method above.
        Args:
            user_subs: existing UserSubscription
            payment_token:str payment method token
            new_plan: SubscriptionPlan
        Steps:
            End existing free subscription.
            Create new Active paid subscription with any signup discounts for which the user is eligible.
        Returns: (Braintree result object, UserSubscription)
        """
        user = user_subs.user
        profile = user.profile
        subs_params = {
            'plan_id': new_plan.planId,
            'trial_duration': 0,
            'payment_method_token': payment_token
        }
        if profile.inviter:
            if profile.affiliateId and Affiliate.objects.filter(user=user.profile.inviter).exists():
                subs_params['convertee_discount'] = True
                logger.info('startActivePaidPlan: apply convertee discount to new subscription for {0}'.format(user))
            else:
                subs_params['invitee_discount'] = True
                logger.info('startActivePaidPlan: apply invitee discount to new subscription for {0}'.format(user))
        # cancel existing subs (status is consistent with the new active subs being eligible for discounts)
        user_subs.status = self.model.CANCELED
        user_subs.display_status = self.model.UI_TRIAL_CANCELED
        user_subs.save()
        # Create new BT subscription. Returns (result, new_user_subs)
        return self.createBtSubscription(user, new_plan, subs_params)


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
                    logger.warning('Invalid display_status for subscriptionId: {0.subscriptionId}'.format(user_subs))
        elif bt_subs.status == self.model.PASTDUE:
            user_subs.display_status = self.model.UI_SUSPENDED
        elif bt_subs.status == self.model.CANCELED:
            if user_subs.display_status not in (self.model.UI_EXPIRED, self.model.UI_SUSPENDED, self.model.UI_TRIAL_CANCELED):
                logger.error('Invalid display_status for canceled subscriptionId: {0.subscriptionId}'.format(user_subs))
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
                if d.quantity < InvitationDiscount.INVITER_MAX_NUM_DISCOUNT:
                    # Update existing row: increment quantity
                    new_quantity = d.quantity + 1
                else:
                    logger.info('Inviter {0.user} has already earned  max discount quantity.'.format(user_subs))
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


    def checkTrialStatus(self, user_subs):
        """Check if user_subs is out of trial period.
        For free plans:
            If trial period is over: switch to UI_TRIAL_CANCELED. This status is
            consistent with: if user starts active paid plan, it will be their first,
            and user is eligible for any signup discounts.
        For BT plans:
            Get up-to-date subscription status from BT and update user_subs as needed.
        Returns: bool if user_subs was updated
        """
        today = timezone.now()
        saved = False
        if user_subs.plan.isFreeIndividual():
            if user_subs.display_status == self.model.UI_TRIAL and (today > user_subs.billingEndDate):
                # free subscription period is over. Switch to UI_TRIAL_CANCELED.
                user_subs.status = self.model.CANCELED
                user_subs.display_status = self.model.UI_TRIAL_CANCELED
                user_subs.save()
                saved = True
        elif user_subs.display_status == self.model.UI_TRIAL and (today > user_subs.billingFirstDate):
            try:
                bt_subs = braintree.Subscription.find(user_subs.subscriptionId)
            except braintree.exceptions.not_found_error.NotFoundError:
                logger.error('checkTrialStatus: subscriptionId:{0.subscriptionId} for user {0.user} not found in BT.'.format(user_subs))
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
        user = user_subs.user
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
    UI_ENTERPRISE_CANCELED = 'Enterprise-Canceled'
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
        (UI_ENTERPRISE_CANCELED, UI_ENTERPRISE_CANCELED)
    )
    RESULT_ALREADY_CANCELED = 'Subscription has already been canceled.'
    MAX_FREE_SUBSCRIPTION_CME = 100000
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

    def inTerminalState(self):
        """Returns True if status is CANCELED or EXPIRED"""
        return self.status == UserSubscription.CANCELED or self.status == UserSubscription.EXPIRED


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

@python_2_unicode_compatible
class CmeBoost(models.Model):
    # fields
    name = models.CharField(max_length=50, unique=True)
    credits = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=6, decimal_places=2, help_text=' in USD', default=0)
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class CmeBoostPurchaseManager(models.Manager):
    def purchaseBoost(self, user, boost, payment_token):
        boost_purchase = None
        # first get the UserCmeCredit instance for this user
        try:
            userCredits = UserCmeCredit.objects.get(user=user)
        except UserCmeCredit.DoesNotExist:
            logger.exception('purchaseBoost: UserCmeCredit does not exist for user {0}'.format(user))
            return
        # Execute Braintree API method for sale: https://developers.braintreepayments.com/reference/request/transaction/sale/python
        result = braintree.Transaction.sale({
            "amount": boost.price,
            "payment_method_token": payment_token,
            "options": {
                "submit_for_settlement": True
            }
        })
        logger.info('purchaseCmeBoost braintree result: {0.is_success}'.format(result))
        if result.is_success:
            # If BT result is success then
            # create new CmeBoostPurchase instance
            bt_trans = result.transaction
            card_type = bt_trans.credit_card.get('card_type')
            card_last4 = bt_trans.credit_card.get('last_4')
            proc_auth_code=bt_trans.processor_authorization_code or ''
            boost_purchase = CmeBoostPurchase.objects.create(
                user=user,
                boost=boost,
                transactionId=bt_trans.id,
                proc_auth_code=proc_auth_code,
                proc_response_code=bt_trans.processor_response_code,
                amount=bt_trans.amount,
                status=bt_trans.status,
                card_type=card_type,
                card_last4=card_last4
            )
            # Update UserCmeCredit instance for the user
            userCredits.boost_credits += boost.credits
            userCredits.save()
        return (result, boost_purchase)

@python_2_unicode_compatible
class CmeBoostPurchase(models.Model):
    user = models.ForeignKey(User,
                             on_delete=models.CASCADE,
                             db_index=True,
                             related_name='cme_boosts',
                             )
    boost = models.ForeignKey(CmeBoost,
                             on_delete=models.CASCADE,
                             db_index=True,
                             related_name='user_boosts',
                             )
    transactionId = models.CharField(max_length=36, unique=True)
    amount = models.DecimalField(max_digits=6, decimal_places=2, help_text=' in USD')
    status = models.CharField(max_length=200, blank=True)
    card_type = models.CharField(max_length=100, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    proc_auth_code = models.CharField(max_length=10, blank=True, help_text='processor_authorization_code')
    proc_response_code = models.CharField(max_length=4, blank=True, help_text='processor_response_code')
    receipt_sent = models.BooleanField(default=False, help_text='set to True on send receipt email')
    failure_alert_sent = models.BooleanField(default=False, help_text='set to True on send payment failure alert via email')
    trans_type = models.CharField(max_length=10, default='sale', help_text='sale or credit')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    objects = CmeBoostPurchaseManager()

    def __str__(self):
        return '{0.user.id} by {0.boost.name}'.format(self)


@python_2_unicode_compatible
class UserCmeCredit(models.Model):
    user = models.OneToOneField(User,
                                on_delete=models.CASCADE,
                                primary_key=True
                                )
    plan_credits = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    boost_credits = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '{0.user.id}: {0.plan_credits}|{0.boost_credits}'.format(self)

    def remaining(self):
        return self.plan_credits + self.boost_credits

    def enough(self, amount):
        return (self.plan_credits + self.boost_credits) >= amount

    def deduct(self, credits):
        if self.enough(credits):
            # deduct from planCredits/boostCredits correspondingly
            if self.plan_credits > 0 and self.plan_credits >= credits:
                # have enough plan credits to redeem the passed amount
                self.plan_credits -= credits
            elif self.plan_credits > 0:
                # not enough plan credits to redeem entire passed amount so take a bite from boost credits
                self.boost_credits -= (credits - self.plan_credits)
                self.plan_credits = 0
            else:
                # plan credits depleted - use boost credits instead
                self.boost_credits -= credits

        return self
