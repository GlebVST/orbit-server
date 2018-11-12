import os
import braintree
import logging
from operator import itemgetter
from pprint import pprint
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import generic, View
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope
from rest_framework import generics, exceptions, permissions, status, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
# proj
from common.logutils import *
# app
from .models import *
from .serializers import UserSubsReadSerializer
from .payment_serializers import *

TPL_DIR = 'users'

logger = logging.getLogger('api.shop')

# https://developers.braintreepayments.com/start/hello-server/python
class GetToken(APIView):
    """Returns Client Token.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def get(self, request, *args, **kwargs):
        context = {
            'token': braintree.ClientToken.generate()
        }
        return Response(context, status=status.HTTP_200_OK)

class SubscriptionPlanList(generics.ListAPIView):
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

    def get_queryset(self):
        """Filter plans by plan_key sourced from the planId in request.user.profile"""
        user = self.request.user
        profile = user.profile
        try:
            plan = SubscriptionPlan.objects.get(planId=profile.planId)
            if plan.isEnterprise():
                filter_kwargs = dict(active=True, plan_type=plan.plan_type)
                return SubscriptionPlan.objects.filter(**filter_kwargs).order_by('id')
            plan_key = plan.plan_key
        except SubscriptionPlan.DoesNotExist:
            logError(logger, self.request, "Invalid profile.planId: {0.planId}".format(profile))
            return SubscriptionPlan.objects.none().order_by('id')
        else:
            if not plan_key:
                plan_key = SubscriptionPlan.objects.findPlanKeyForProfile(profile)
                if not plan_key:
                    plan_key = SubscriptionPlanKey.objects.all().order_by('id')[0]
            # return plans for the plan_key
            filter_kwargs = dict(active=True, plan_key=plan_key)
            return SubscriptionPlan.objects.filter(**filter_kwargs).order_by('price','pk')


# SubscriptionPlanPublic : for AllowAny
class SubscriptionPlanPublic(generics.ListAPIView):
    """Returns a list of eligible plans for a given landing page key using the SubscriptionPlanPublicSerializer
    """
    serializer_class = SubscriptionPlanPublicSerializer
    permission_classes = (permissions.AllowAny,)

    def get_queryset(self):
        """Filter plans by plan_key in url using iexact search"""
        lkey = self.kwargs['landing_key']
        if lkey.endswith('/'):
            lkey = lkey[0:-1]
        try:
            plan_key = SubscriptionPlanKey.objects.get(name__iexact=lkey)
        except SubscriptionPlanKey.DoesNotExist:
            logWarning(logger, self.request, "Invalid key: {0}".format(lkey))
            return SubscriptionPlan.objects.none().order_by('id')
        else:
            return SubscriptionPlan.objects.getPlansForKey(plan_key)


class SignupDiscountList(APIView):
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get(self, request, *args, **kwargs):
        user = request.user
        profile = user.profile
        data = []
        if UserSubscription.objects.allowSignupDiscount(user):
            promo = SignupEmailPromo.objects.get_casei(user.email)
            if promo:
                # this overrides any other discount
                plan = SubscriptionPlan.objects.get(planId=profile.planId)
                d = Discount.objects.get(discountType=BASE_DISCOUNT_TYPE, activeForType=True)
                discount_amount = plan.discountPrice - promo.first_year_price
                data = [{
                    'discountId': d.discountId,
                    'amount': discount_amount,
                    'displayLabel': promo.display_label,
                    'discountType': 'signup-email'
                }]
            else:
                discounts = UserSubscription.objects.getDiscountsForNewSubscription(user)
                data = [{
                    'discountId': d['discount'].discountId,
                    'amount': d['discount'].amount,
                    'discountType': d['discountType'],
                    'displayLabel': d['displayLabel']
                    } for d in discounts]
        # sort by amount desc
        display_data = sorted(data, key=itemgetter('amount'), reverse=True)
        context = {'discounts': display_data}
        return Response(context, status=status.HTTP_200_OK)


class GetPaymentMethods(APIView):
    """
    Returns a list of existing payment methods from the Customer vault (if any).

    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def get(self, request, *args, **kwargs):
        try:
            customer = Customer.objects.get(user=request.user)
            results = Customer.objects.getPaymentMethods(customer)
        except Customer.DoesNotExist:
            results = []
        except braintree.exceptions.not_found_error.NotFoundError:
            logWarning(logger, request, "BT Customer not found: {0.user}".format(request))
            results = []
        finally:
            return Response(results, status=status.HTTP_200_OK)


class UpdatePaymentToken(APIView):
    """
    This view updates the existing payment_token for a
    customer using a new nonce (e.g. to update an expired
    card).
    It expects the Customer Vault to only contain 1 token.
    If more than 1 token is found, it returns 400 error
    unless a payment_token is explicitly provided to update.
    Example JSON:
    {
      "payment-method-nonce":"abcd-efg"
    }
    Example JSON with token (only used if Customer has multiple tokens in Vault):
    {
      "payment-method-token":"5wfrrp"
      "payment-method-nonce":"abcd-efg"
    }
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, *args, **kwargs):
        context = {}
        userdata = request.data
        payment_nonce = userdata.get('payment-method-nonce', None)
        payment_token = userdata.get('payment-method-token', None)
        # some basic validation for incoming parameters
        if not payment_nonce:
            context = {
                'success': False,
                'message': 'Payment Nonce is required.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # get customer object from database
        try:
            customer = Customer.objects.get(user=request.user)
            bc = Customer.objects.findBtCustomer(customer)
        except Customer.DoesNotExist:
            context = {
                'success': False,
                'message': 'Local Customer object not found for user.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        except braintree.exceptions.not_found_error.NotFoundError:
            context = {
                'success': False,
                'message': 'BT Customer object not found.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # Get existing tokens for customer
        tokens = [m.token for m in bc.payment_methods]
        num_tokens = len(tokens)
        if not num_tokens:
            context = {
                'success': False,
                'message': 'BT Customer has no existing tokens to update.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        if num_tokens == 1:
            payment_token = tokens[0]
        elif payment_token is None:
            # Multiple tokens exist and request did not specify a token
            context = {
                'success': False,
                'message': 'BT Customer has multiple existing tokens. Request must specify the token to update.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        elif payment_token not in tokens:
            context = {
                'success': False,
                'message': 'Invalid Payment Token - does not exist for Customer.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # Update Customer
        result = Customer.objects.updatePaymentMethod(customer, payment_nonce, payment_token)
        context = {
            'success': result.is_success
        }
        if not result.is_success:
            context['message'] = 'UpdatePaymentToken: Customer vault update failed.'
            message = 'UpdatePaymentToken: Customer vault update failed. Result message: {0.message}'.format(result)
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            logInfo(logger, request, 'UpdatePaymentToken complete')
            return Response(context, status=status.HTTP_200_OK)



class NewSubscription(generics.CreateAPIView):
    """Create Active Braintree subscription for the user.
    User must not have a current active subscription of any type.
    This view expects a JSON object in the POST data:
    Example when using existing customer payment method with token obtained from Vault:
        {"payment_method_token":"5wfrrp", "do_trial":0}

    Example when using a new payment method with a Nonce prepared on client:
        {"payment_method_nonce":"cd36493e_f883_48c2_aef8_3789ee3569a9", "do_trial":0}
    If a Nonce is given, it takes precedence and will be saved to the Customer vault and converted into a token.
    If do_trial == 0: the trial period is skipped and the subscription starts immediately.
    If do_trial == 1 (or key not present), the trial period is activated. This is the default.
    """
    serializer_class = CreateUserSubsSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def perform_create(self, serializer, format=None):
        user = self.request.user
        with transaction.atomic():
            result, user_subs = serializer.save(user=user)
        return (result, user_subs)

    def create(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        # first check if user is allowed to create a new subscription
        logDebug(logger, request, 'NewSubscription begin')
        profile = request.user.profile
        if not UserSubscription.objects.allowNewSubscription(request.user):
            context = {
                'success': False,
                'message': 'User has an existing Subscription that must be canceled first.'
            }
            logError(logger, request, context['message'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # form_data will be modified before passing it to serializer
        form_data = request.data.copy()
        payment_nonce = form_data.get('payment_method_nonce', None)
        payment_token = form_data.get('payment_method_token', None)
        trial_duration = form_data.get('trial_duration', None)
        default_do_trial = 1 if trial_duration else 0
        do_trial = form_data.get('do_trial', default_do_trial)
        if do_trial not in (0, 1):
            context = {
                'success': False,
                'message': 'do_trial value must be either 0 or 1'
            }
            logError(logger, request, context['message'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)

        # Get last subscription of User (if any)
        last_subscription = UserSubscription.objects.getLatestSubscription(request.user)
        # If user has had a prior subscription, do_trial must be 0
        if last_subscription:
            if do_trial:
                context = {
                    'success': False,
                    'message': 'Renewing subscription is not permitted a trial period.'
                }
                message = context['message'] + ' last_subscription id: {0}'.format(last_subscription.pk)
                logError(logger, request, message)
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            # check pastdue
            if last_subscription.status == UserSubscription.PASTDUE:
                logInfo(logger, request, 'NewSubscription: cancel existing pastdue subs {0.subscriptionId}'.format(last_subscription))
                cancel_result = UserSubscription.objects.terminalCancelBtSubscription(last_subscription)
                if not cancel_result.is_success:
                    if cancel_result.message == UserSubscription.RESULT_ALREADY_CANCELED:
                        logInfo(logger, request, 'Existing bt_subs already canceled. Syncing with db.')
                        bt_subs = UserSubscription.objects.findBtSubscription(last_subscription.subscriptionId)
                        UserSubscription.objects.updateSubscriptionFromBt(last_subscription, bt_subs)
                    else:
                        context = {
                            'success': False,
                            'message': 'Cancel Suspended Subscription failed.'
                        }
                        message = 'NewSubscription: Cancel pastdue subs failed. Result message: {0.message}'.format(cancel_result)
                        logError(logger, request, message)
                        return Response(context, status=status.HTTP_400_BAD_REQUEST)
        invitee_discount = False
        convertee_discount = False # used for affiliate conversion
        if profile.inviter and ((last_subscription is None) or (last_subscription.display_status == UserSubscription.UI_TRIAL_CANCELED)):
            if profile.affiliateId and Affiliate.objects.filter(user=profile.inviter).exists():
                # profile.inviter is an Affiliate and user was converted by one of their affiliateId
                convertee_discount = True # profile.inviter is an affiliate
            else:
                invitee_discount = True

        # get local customer object and braintree customer
        customer = request.user.customer
        try:
            bc = Customer.objects.findBtCustomer(customer)
        except braintree.exceptions.not_found_error.NotFoundError:
            context = {
                'success': False,
                'message': 'BT Customer object not found.'
            }
            message = context['message'] + ' customerId: {0.customerId}'.format(customer)
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # Convert nonce into token because it is required by subs
        if payment_nonce:
            # If user has multiple tokens, then delete their tokens
            Customer.objects.makeSureNoMultipleMethods(customer)
            try:
                result = Customer.objects.addOrUpdatePaymentMethod(customer, payment_nonce)
            except ValueError, e:
                context = {
                    'success': False,
                    'message': str(e)
                }
                logException(logger, request, 'NewSubscription addOrUpdatePaymentMethod ValueError')
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            if not result.is_success:
                message = 'Customer vault update failed. Result message: {0.message}'.format(result)
                context = {
                    'success': False,
                    'message': message
                }
                logError(logger, request, message)
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            bc2 = Customer.objects.findBtCustomer(customer)
            tokens = [m.token for m in bc2.payment_methods]
            payment_token = tokens[0]
        # finally update form_data for serializer
        form_data['payment_method_token'] = payment_token
        form_data['invitee_discount'] = invitee_discount
        form_data['convertee_discount'] = convertee_discount
        if not do_trial:
            form_data['trial_duration'] = 0 # 0 days of trial. Subs starts immediately
        # set plan from profile.planId
        form_data['plan'] = SubscriptionPlan.objects.get(planId=profile.planId).pk
        logDebug(logger, request, str(form_data))
        in_serializer = self.get_serializer(data=form_data)
        in_serializer.is_valid(raise_exception=True)
        result, user_subs = self.perform_create(in_serializer)
        context = {'success': result.is_success}
        if not result.is_success:
            message = 'NewSubscription: Create Subscription failed. Result message: {0.message}'.format(result)
            context['message'] = message
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        logInfo(logger, request, 'NewSubscription: complete for subscriptionId={0.subscriptionId}'.format(user_subs))
        out_serializer = UserSubsReadSerializer(user_subs)
        context['subscription'] = out_serializer.data
        return Response(context, status=status.HTTP_201_CREATED)

class ActivatePaidSubscription(generics.CreateAPIView):
    """
    This expects a nonce in the POST data:
        {"payment_method_nonce":"cd36493e_f883_48c2_aef8_3789ee3569a9"}
    Switch user from free plan to their first active subscription on paid plan: BT Standard Plan that shares the same plan_key as the user's current free plan.
    It creates new active BT subscription with no trial period (billing starts immediately).
    """
    serializer_class = ActivatePaidUserSubsSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def perform_create(self, serializer, format=None):
        user = self.request.user
        last_subscription = UserSubscription.objects.getLatestSubscription(user)
        with transaction.atomic():
            result, user_subs = serializer.save(user_subs=last_subscription)
        return (result, user_subs)

    def create(self, request, *args, **kwargs):
        logDebug(logger, request, 'ActivatePaidSubscription begin')
        user = request.user
        profile = user.profile
        last_subscription = UserSubscription.objects.getLatestSubscription(user)
        old_plan = last_subscription.plan
        if old_plan.isPaid():
            context = {
                'success': False,
                'message': 'Current subscription already requires payment method.'
            }
            message = context['message'] + ' last_subscription id: {0}'.format(last_subscription.pk)
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # get the partner paid standard plan
        try:
            new_plan = SubscriptionPlan.objects.getPaidPlanForFreePlan(old_plan)
        except SubscriptionPlan.DoesNotExist:
            context = {
                'success': False,
                'message': 'Partner paid plan does not exist.'
            }
            message = context['message'] + ' last_subscription id: {0}'.format(last_subscription.pk)
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)

        # get local customer object and braintree customer
        customer = user.customer
        try:
            bc = Customer.objects.findBtCustomer(customer)
        except braintree.exceptions.not_found_error.NotFoundError:
            context = {
                'success': False,
                'message': 'BT Customer object not found.'
            }
            message = context['message'] + ' customerId: {0.customerId}'.format(customer)
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)

        # form_data will be modified before passing it to serializer
        form_data = request.data.copy()
        payment_nonce = form_data['payment_method_nonce']
        # Convert nonce into token because it is required by subs
        # If user has multiple tokens, then delete their tokens
        Customer.objects.makeSureNoMultipleMethods(customer)
        try:
            result = Customer.objects.addOrUpdatePaymentMethod(customer, payment_nonce)
        except ValueError, e:
            context = {
                'success': False,
                'message': str(e)
            }
            logException(logger, request, 'ActivatePaidSubscription: addOrUpdatePaymentMethod ValueError')
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        if not result.is_success:
            message = 'ActivatePaidSubscription: Customer vault update failed. Result message: {0.message}'.format(result)
            context = {
                'success': False,
                'message': message
            }
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        bc2 = Customer.objects.findBtCustomer(customer)
        tokens = [m.token for m in bc2.payment_methods]
        payment_token = tokens[0]
        # finally update form_data for serializer
        form_data['payment_method_token'] = payment_token
        form_data['plan'] = new_plan.pk
        logDebug(logger, request, str(form_data))
        in_serializer = self.get_serializer(data=form_data)
        in_serializer.is_valid(raise_exception=True)
        result, user_subs = self.perform_create(in_serializer)
        context = {'success': result.is_success}
        if not result.is_success:
            message = 'ActivatePaidSubscription: Create Subscription failed. Result message: {0.message}'.format(result)
            context['message'] = message
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        logInfo(logger, request, 'ActivatePaidSubscription: complete for subscriptionId={0.subscriptionId}'.format(user_subs))
        out_serializer = UserSubsReadSerializer(user_subs)
        context['subscription'] = out_serializer.data
        pdata = UserSubscription.objects.serialize_permissions(user, user_subs)
        context['permissions'] = pdata['permissions']
        context['credits'] = pdata['credits']
        return Response(context, status=status.HTTP_201_CREATED)


class UpgradePlanAmount(APIView):
    """This calculates the amount the user will be charged for upgrading to the new higher-priced plan. If user's current subscription status is not Active, the user cannot upgrade.
    Example response
    """
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)
    def get(self, request, *args, **kwargs):
        try:
            new_plan = SubscriptionPlan.objects.get(pk=kwargs['plan_pk'])
        except SubscriptionPlan.DoesNotExist:
            context = {
                'can_upgrade': False,
                'message': 'Invalid Plan.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # user must have an existing subscription
        user = request.user
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        if not user_subs:
            context = {
                'can_upgrade': False,
                'message': 'No existing subscription found.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # New plan must be an upgrade from the old plan
        old_plan = user_subs.plan
        if new_plan.price < old_plan.price:
            context = {
                'can_upgrade': False,
                'message': 'Current subscription plan is {0.plan}.'.format(user_subs)
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        starterStatus = (UserSubscription.UI_TRIAL, UserSubscription.UI_TRIAL_CANCELED, UserSubscription.UI_ENTERPRISE_CANCELED, UserSubscription.UI_SUSPENDED)
        if user_subs.display_status in starterStatus:
            # For pastdue, billingDay is effectively 0 since user has not paid, and treat it the same as Trial for the calculation of owed.
            owed = new_plan.discountPrice
            discounts = UserSubscription.objects.getDiscountsForNewSubscription(user)
            for d in discounts:
                owed -= d['discount'].amount
            can_upgrade = True
            message = ''
            if user_subs.status == UserSubscription.UI_SUSPENDED:
                can_upgrade = False # UI will redirect to credit card screen
                message = 'Please enter a valid credit card for the new subscription'
            context = {
                'can_upgrade': can_upgrade,
                'amount': owed.quantize(TWO_PLACES, ROUND_HALF_UP),
                'message': message,
            }
            return Response(context, status=status.HTTP_200_OK)
        if user_subs.display_status == UserSubscription.UI_ACTIVE_DOWNGRADE:
            # user is already in upgraded plan (can re-activate to cancel the scheduled downgrade)
            context = {
                'can_upgrade': True,
                'amount': 0,
                'message': '',
            }
            return Response(context, status=status.HTTP_200_OK)
        if user_subs.status == UserSubscription.EXPIRED:
            # user's last subscription is expired (this is the final state AFTER Active-Canceled)
            # so they have already used up their first year (hence no proration on plan first-year discount at all).
            owed = new_plan.price
            context = {
                'can_upgrade': True,
                'amount': owed.quantize(TWO_PLACES, ROUND_HALF_UP),
                'message': '',
            }
            return Response(context, status=status.HTTP_200_OK)
        if user_subs.status == UserSubscription.ACTIVE:
            # if Active: user_subs.display_status is one of Active/Active-Canceled
            if user_subs.billingCycle > 1:
                # already used up their first year (no proration on plan first-year discount at all).
                owed = new_plan.price
                discount_amount = 0
            else:
                # need to calculate proration
                now = timezone.now()
                daysInYear = 365 if not calendar.isleap(now.year) else 366
                td = now - user_subs.billingStartDate
                billingDay = td.days
                owed, discount_amount = UserSubscription.objects.getDiscountAmountForUpgrade(
                        old_plan, new_plan, user_subs.billingCycle, billingDay, daysInYear)
                logDebug(logger, request, 'SubscriptionId:{0.subscriptionId}|Cycle:{0.billingCycle}|Day:{1}|Owed:{2}|Discount:{3}'.format(
                    user_subs,
                    billingDay,
                    owed.quantize(TWO_PLACES, ROUND_HALF_UP),
                    discount_amount.quantize(TWO_PLACES, ROUND_HALF_UP)
                ))
            apply_earned_discount = False
            # check for earned discounts
            if (user_subs.display_status == UserSubscription.UI_ACTIVE) and (old_plan.price > user_subs.nextBillingAmount):
                # user has earned some discounts that would have been applied to the next billing cycle on their old plan
                # (Active-Canceled users forfeited any earned discounts because they don't have a nextBillingAmount)
                earned_discount_amount = old_plan.price - user_subs.nextBillingAmount
                # check if can apply the earned_discount_amount right now
                t = discount_amount + earned_discount_amount
                if t < new_plan.price:
                    discount_amount = t
                    owed -= earned_discount_amount
                    apply_earned_discount = True
                    logDebug(logger, request, 'earned_discount_amount {0}'.format(earned_discount_amount))
            context = {
                'can_upgrade': True,
                'amount': owed.quantize(TWO_PLACES, ROUND_HALF_UP),
                'message': '',
                'apply_earned_discount': apply_earned_discount
            }
            return Response(context, status=status.HTTP_200_OK)
        if user_subs.status == UserSubscription.CANCELED and user_subs.display_status == UserSubscription.UI_EXPIRED:
            # user_subs was terminally canceled (not active-canceled or natural expire).
            # Since they may have gotten refund, cannot calculate any proration.
            owed = new_plan.price
            context = {
                'can_upgrade': True,
                'amount': owed.quantize(TWO_PLACES, ROUND_HALF_UP),
                'message': '',
            }
            return Response(context, status=status.HTTP_200_OK)
        # if get here, logError
        context = {
            'can_upgrade': False,
            'message': 'Unhandled subscription status: {0.pk}|{0.status}|{0.display_status}'.format(user_subs)
        }
        logError(logger, request, context['message'])
        return Response(context, status=status.HTTP_200_OK)


class UpgradePlan(generics.CreateAPIView):
    """Plan upgrade (means to a higher-priced plan).
    Cancel existing subscription if necessary, and create new UserSubscription under the new plan for the user.
    This view expects a JSON object in the POST data:
        Example when using existing customer payment method with token obtained from Vault:
            {"plan":3,"payment_method_token":"5wfrrp"}
        Example when using a new payment method with a Nonce prepared on client:
            {"plan":3,"payment_method_nonce":"cd36493e_f883_48c2_aef8_3789ee3569a9"}
    If a Nonce is given, it takes precedence and will be saved to the Customer vault and converted into a token.
    """
    serializer_class = UpgradePlanSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def perform_create(self, serializer, format=None):
        with transaction.atomic():
            result, new_user_subs = serializer.save(user_subs=self.user_subs)
        return (result, new_user_subs)

    def create(self, request, *args, **kwargs):
        logDebug(logger, request, 'UpgradePlan begin')
        user = request.user
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        if not user_subs:
            # this endpoint is for upgrade only. An existing subs must exist.
            context = {
                'success': False,
                'message': 'No existing subscription found.'
            }
            logError(logger, request, context['message'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        if user_subs.status == UserSubscription.PASTDUE:
            logInfo(logger, request, 'UpgradePlan: cancel existing pastdue subs {0.subscriptionId}'.format(user_subs))
            cancel_result = UserSubscription.objects.terminalCancelBtSubscription(user_subs)
            if not cancel_result.is_success:
                if cancel_result.message == UserSubscription.RESULT_ALREADY_CANCELED:
                    logInfo(logger, request, 'Existing bt_subs already canceled. Syncing with db.')
                    bt_subs = UserSubscription.objects.findBtSubscription(user_subs.subscriptionId)
                    UserSubscription.objects.updateSubscriptionFromBt(user_subs, bt_subs)
                else:
                    context = {
                        'success': False,
                        'message': 'Cancel Suspended Subscription failed.'
                    }
                    message = 'UpgradePlan: Cancel pastdue subs failed. Result message: {0.message}'.format(cancel_result)
                    logError(logger, request, message)
                    return Response(context, status=status.HTTP_400_BAD_REQUEST)
        self.user_subs = user_subs
        form_data = request.data.copy()
        logDebug(logger, request, str(form_data))
        payment_token = form_data.get('payment_method_token', None)
        payment_nonce = form_data.get('payment_method_nonce', None)
        if payment_nonce:
            # Convert nonce into token because it is required by subs
            customer = user.customer
            try:
                pm_result = Customer.objects.addOrUpdatePaymentMethod(customer, payment_nonce)
            except braintree.exceptions.not_found_error.NotFoundError:
                context = {
                    'success': False,
                    'message': 'BT Customer object not found.'
                }
                message = context['message'] + ' customerId: {0.customerId}'.format(customer)
                logError(logger, request, message)
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            except ValueError, e:
                context = {
                    'success': False,
                    'message': str(e)
                }
                logException(logger, request, 'UpgradePlan addOrUpdatePaymentMethod ValueError')
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            # Get converted token
            if not pm_result.is_success:
                message = 'UpgradePlan: Customer vault update failed. Result message: {0.message}'.format(pm_result)
                context = {
                    'success': False,
                    'message': message
                }
                logError(logger, request, message)
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            bc = Customer.objects.findBtCustomer(customer)
            tokens = [m.token for m in bc.payment_methods]
            payment_token = tokens[0]
        # update form_data for serializer
        form_data['payment_method_token'] = payment_token
        in_serializer = self.get_serializer(data=form_data)
        in_serializer.is_valid(raise_exception=True)
        result, new_user_subs = self.perform_create(in_serializer)
        context = {'success': result.is_success}
        if not result.is_success:
            message = 'UpgradePlan failed. Result message: {0.message}'.format(result)
            context['message'] = message
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        logInfo(logger, request, 'UpgradePlan: complete for subscriptionId={0.subscriptionId}'.format(new_user_subs))
        out_serializer = UserSubsReadSerializer(new_user_subs)
        context['subscription'] = out_serializer.data
        # Return permissions b/c new_user_subs may allow different perms than prior subscription.
        pdata = UserSubscription.objects.serialize_permissions(user, new_user_subs)
        context['permissions'] = pdata['permissions']
        context['credits'] = pdata['credits']
        return Response(context, status=status.HTTP_201_CREATED)


class DowngradePlan(APIView):
    """
    User is currently in Plus plan and wants to downgrade back to Standard.
    This will take effect at the end of the current billing cycle.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, *args, **kwargs):
        user_subs = UserSubscription.objects.getLatestSubscription(request.user)
        try:
            result = UserSubscription.objects.makeActiveDowngrade(user_subs)
        except:
            context = {
                'success': False,
                'message': 'BT Subscription not found.'
            }
            message = 'DowngradePlan: BT Subscription not found for subscriptionId: {0.subscriptionId}'.format(user_subs)
            logException(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            if not result.is_success:
                context = {
                    'success': False,
                    'message': 'BT Subscription update failed.'
                }
                message = 'DowngradePlan failed for subscriptionId: {0.subscriptionId}. Result message: {1.message}'.format(user_subs, result)
                logError(logger, request, message)
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            else:
                context = {
                    'success': True,
                    'bt_status': user_subs.status,
                    'display_status': user_subs.display_status
                }
                message = 'DowngradePlan set for subscriptionId: {0.subscriptionId}.'.format(user_subs)
                logInfo(logger, request, message)
                return Response(context, status=status.HTTP_200_OK)


class SwitchTrialToActive(APIView):
    """
    This view cancels the user's Trial subscription, and creates a new
    Active subscription.
    Example JSON when using existing customer payment method with token obtained from Vault:
        {"payment-method-token":"5wfrrp"}
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, *args, **kwargs):
        # 1. check that user is currently in UI_TRIAL
        last_subscription = UserSubscription.objects.getLatestSubscription(request.user)
        if not last_subscription or (last_subscription.display_status != UserSubscription.UI_TRIAL):
            context = {
                'success': False,
                'message': 'User is not currently in Trial period.'
            }
            logError(logger, request, context['message'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        userdata = request.data
        payment_token = userdata.get('payment-method-token', None)
        if not payment_token:
            context = {
                'success': False,
                'message': 'Payment Method Token is required'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)

        # Cancel old subscription and create new Active subscription
        with transaction.atomic():
            result, user_subs = UserSubscription.objects.switchTrialToActive(last_subscription, payment_token)
        context = {'success': result.is_success}
        if not result.is_success:
            context['message'] = 'Create Subscription failed.'
            message = 'SwitchTrialToActive: Create Subscription failed. Result message: {0.message}'.format(result)
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context['subscriptionId'] = user_subs.subscriptionId
            context['bt_status'] = user_subs.status
            context['display_status'] = user_subs.display_status
            context['billingStartDate'] = user_subs.billingStartDate
            context['billingEndDate'] = user_subs.billingEndDate
            logInfo(logger, request, 'SwitchTrialToActive complete for subscriptionId={0.subscriptionId}'.format(user_subs))
        return Response(context, status=status.HTTP_201_CREATED)


class CancelSubscription(APIView):
    """
    This view expects a JSON object in the POST data:
    {"subscription-id": BT subscriptionid to cancel}
    If the subscription Id is valid:
        If the subscription is in UI_TRIAL:
            call terminalCancelBtSubscription
        If the subscription is in UI_ACTIVE:
            call makeActiveCanceled
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, *args, **kwargs):
        userdata = request.data
        subscriptionId = userdata.get('subscription-id', None)
        if not subscriptionId:
            context = {
                'success': False,
                'message': 'BT SubscriptionId is required'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        try:
            user_subs = UserSubscription.objects.get(
                user=request.user,
                subscriptionId=subscriptionId
            )
        except UserSubscription.DoesNotExist:
            context = {
                'success': False,
                'message': 'UserSubscription local object not found.'
            }
            message = context['message'] + ' BT subscriptionId: {0}'.format(subscriptionId)
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # check current status
        if user_subs.display_status not in (UserSubscription.UI_ACTIVE, UserSubscription.UI_TRIAL):
            context = {
                'success': False,
                'message': 'UserSubscription status is already: ' + user_subs.display_status
            }
            logError(logger, request, context['message'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # proceed with cancel
        try:
            if user_subs.display_status == UserSubscription.UI_TRIAL:
                result = UserSubscription.objects.terminalCancelBtSubscription(user_subs)
            else:
                result = UserSubscription.objects.makeActiveCanceled(user_subs)
        except braintree.exceptions.not_found_error.NotFoundError:
            context = {
                'success': False,
                'message': 'BT Subscription not found.'
            }
            message = 'CancelSubscription: BT Subscription not found for subscriptionId: {0.subscriptionId}'.format(user_subs)
            logException(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            if not result.is_success:
                context = {
                    'success': False,
                    'message': 'BT Subscription update failed.'
                }
                message = 'CancelSubscription failed for subscriptionId: {0.subscriptionId}. Result message: {1.message}'.format(user_subs, result)
                logError(logger, request, message)
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            else:
                context = {
                    'success': True,
                    'bt_status': user_subs.status,
                    'display_status': user_subs.display_status
                }
                message = 'CancelSubscription complete for subscriptionId: {0.subscriptionId}.'.format(user_subs)
                logInfo(logger, request, message)
                return Response(context, status=status.HTTP_200_OK)


class ResumeSubscription(APIView):
    """
    This view expects a JSON object from the POST:
    {"subscription-id": BT subscriptionid to cancel}
    If the subscription Id is valid and it is in UI_ACTIVE_CANCELED:
            call reactivateBtSubscription
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, *args, **kwargs):
        userdata = request.data
        subscriptionId = userdata.get('subscription-id', None)
        if not subscriptionId:
            context = {
                'success': False,
                'message': 'BT subscription-id is required'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        try:
            user_subs = UserSubscription.objects.get(
                user=request.user,
                subscriptionId=subscriptionId
            )
        except UserSubscription.DoesNotExist:
            context = {
                'success': False,
                'message': 'UserSubscription local object not found.'
            }
            message = context['message'] + ' BT subscriptionId: {0}'.format(subscriptionId)
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # check current status
        if user_subs.display_status not in (UserSubscription.UI_ACTIVE_CANCELED, UserSubscription.UI_ACTIVE_DOWNGRADE):
            context = {
                'success': False,
                'message': 'UserSubscription status is already: ' + user_subs.display_status
            }
            message = context['message'] + ' BT subscriptionId: {0}'.format(subscriptionId)
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # proceed with reactivate
        try:
            result = UserSubscription.objects.reactivateBtSubscription(user_subs)
        except braintree.exceptions.not_found_error.NotFoundError:
            context = {
                'success': False,
                'message': 'BT Subscription not found.'
            }
            message = 'ResumeSubscription: BT Subscription not found for subscriptionId: {0.subscriptionId}'.format(user_subs)
            logException(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        except ValueError, e:
            context = {
                'success': False,
                'message': str(e)
            }
            logException(logger, request, 'ResumeSubscription ValueError')
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            if not result.is_success:
                context = {
                    'success': False,
                    'message': 'BT Subscription update failed.'
                }
                message = 'ResumeSubscription failed for subscriptionId: {0.subscriptionId}. Result message: {1.message}'.format(user_subs, result)
                logError(logger, request, message)
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            else:
                context = {
                    'success': True,
                    'bt_status': user_subs.status,
                    'display_status': user_subs.display_status
                }
                message = 'ResumeSubscription complete for subscriptionId: {0.subscriptionId}.'.format(user_subs)
                logInfo(logger, request, message)
                return Response(context, status=status.HTTP_200_OK)

class CmeBoostList(generics.ListAPIView):
    queryset = CmeBoost.objects.filter(active=True).order_by('credits')
    serializer_class = CmeBoostSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

class CmeBoostPurchase(generics.CreateAPIView):
    serializer_class = CmeBoostPurchaseSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def perform_create(self, serializer, format=None):
        user = self.request.user
        with transaction.atomic():
            result, boost_purchase = serializer.save(user=user)
        return (result, boost_purchase)

    def create(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""

        logDebug(logger, request, 'Purchase CME Boost')
        user = request.user
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        # form_data will be modified before passing it to serializer
        form_data = request.data.copy()
        payment_nonce = form_data.get('payment_method_nonce', None)
        payment_token = form_data.get('payment_method_token', None)

        # get local customer object and braintree customer
        customer = user.customer
        try:
            bc = Customer.objects.findBtCustomer(customer)
        except braintree.exceptions.not_found_error.NotFoundError:
            context = {
                'success': False,
                'message': 'BT Customer object not found.'
            }
            message = context['message'] + ' customerId: {0.customerId}'.format(customer)
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)

        # Convert nonce into token because it is required by subs
        if payment_nonce:
            # If user has multiple tokens, then delete their tokens
            Customer.objects.makeSureNoMultipleMethods(customer)
            try:
                result = Customer.objects.addOrUpdatePaymentMethod(customer, payment_nonce)
            except ValueError, e:
                context = {
                    'success': False,
                    'message': str(e)
                }
                logException(logger, request, 'NewSubscription addOrUpdatePaymentMethod ValueError')
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            if not result.is_success:
                message = 'Customer vault update failed. Result message: {0.message}'.format(result)
                context = {
                    'success': False,
                    'message': message
                }
                logError(logger, request, message)
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            bc2 = Customer.objects.findBtCustomer(customer)
            tokens = [m.token for m in bc2.payment_methods]
            payment_token = tokens[0]

        # finally update form_data for serializer
        form_data['payment_method_token'] = payment_token

        # set plan from profile.planId
        # form_data['plan'] = SubscriptionPlan.objects.get(planId=profile.planId).pk
        logDebug(logger, request, str(form_data))
        in_serializer = self.get_serializer(data=form_data)
        in_serializer.is_valid(raise_exception=True)
        result, boost_purchase = self.perform_create(in_serializer)
        context = {'success': result.is_success}
        if not result.is_success:
            message = 'CME Boost Purchase failed. Result message: {0.message}'.format(result)
            context['message'] = message
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        logInfo(logger, request, 'CME Boost Purchase complete for user {0.id}: {1.id}'.format(user, boost_purchase))
        out_serializer = CmeBoostPurchaseSerializer(boost_purchase)
        context['boost'] = out_serializer.data
        # Return permissions b/c new CME Boost may allow different perms than prior to purchase
        pdata = UserSubscription.objects.serialize_permissions(user, user_subs)
        context['permissions'] = pdata['permissions']
        context['credits'] = pdata['credits']
        return Response(context, status=status.HTTP_201_CREATED)

#
# testing only
#
@method_decorator(login_required, name='dispatch')
class TestForm(generic.TemplateView):
    template_name = os.path.join(TPL_DIR, 'payment_test_form.html')
    def get_context_data(self, **kwargs):
        context = super(TestForm, self).get_context_data(**kwargs)
        context['token'] = braintree.ClientToken.generate()
        context['user'] = self.request.user
        return context

@method_decorator(login_required, name='dispatch')
class TestFormCheckout(View):
    """
    This view expects a JSON object from the POST with Braintree transaction details.
    Example JSON when using a new payment method with a Nonce prepared on client:
    {"payment-method-nonce":"cd36493e-f883-48c2-aef8-3789ee3569a9"}
    """
    from django.http import JsonResponse
    def post(self, request, *args, **kwargs):
        context = {}
        userdata = request.POST.copy()
        pprint(userdata)
        payment_nonce = userdata['payment-method-nonce']
        # get customer object from database
        customer = Customer.objects.get(user=request.user)
        # prepare transaction details
        transaction_params = {
            "amount": 3,
            "options": {
                "submit_for_settlement": True
            }
        }
        # new card payment - need to associate with the customer in Braintree's Vault on success
        transaction_params.update({
            "payment_method_nonce": payment_nonce,
            "customer_id": str(customer.customerId),
            "options": {
                "store_in_vault_on_success": True
            }
        })
        # https://developers.braintreepayments.com/reference/request/transaction/sale/python
        # https://developers.braintreepayments.com/reference/response/transaction/python#result-object
        result = braintree.Transaction.sale(transaction_params)
        success = result.is_success # bool
        pprint(result)
        context['success'] = success
        if success:
            trans_status = result.transaction.status # don't call it status because it override DRF status
            context['status'] = trans_status
            context['transactionid'] = result.transaction.id
            return JsonResponse(context)
        else:
            if hasattr(result, 'transaction') and result.transaction is not None:
                trans_status = result.transaction.status
                context['status'] = trans_status
            else:
                # validation error
                context['status'] = 'validation_error'
                context['validation_errors'] = []
                for error in result.errors.deep_errors:
                    context['validation_errors'].append({
                        'attribute': error.attribute,
                        'code': error.code,
                        'message': error.message
                    })
            return JsonResponse(context, status=400)
