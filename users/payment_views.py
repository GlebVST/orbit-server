import os
import braintree
import datetime
from datetime import timedelta
import logging
from pprint import pprint
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import generic
from oauth2_provider.ext.rest_framework import TokenHasReadWriteScope, TokenHasScope
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
# proj
from common.logutils import *
# app
from .models import *

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
        else:
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



class NewSubscription(APIView):
    """
    This view expects a JSON object in the POST data:
    Example JSON when using existing customer payment method with token obtained from Vault:
        {"plan-id":1,"payment-method-token":"5wfrrp", "do-trial":0}

    Example JSON when using a new payment method with a Nonce prepared on client:
        {"plan-id":1,"payment-method-nonce":"cd36493e-f883-48c2-aef8-3789ee3569a9", "do-trial":0}
    If do-trial == 0: the trial period is skipped and the subscription starts immediately.
    If do-trial == 1 (or key not present), the trial period is activated. This is the default.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, *args, **kwargs):
        # first check if user is allowed to create a new subscription
        if not UserSubscription.objects.allowNewSubscription(request.user):
            context = {
                'success': False,
                'message': 'User has an existing Subscription that must be canceled first.'
            }
            logError(logger, request, context['message'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        userdata = request.data
        # some basic validation for incoming parameters
        payment_nonce = userdata.get('payment-method-nonce', None)
        payment_token = userdata.get('payment-method-token', None)
        if not payment_nonce and not payment_token:
            context = {
                'success': False,
                'message': 'Payment Nonce or Method Token is required'
            }
            logError(logger, request, context['message'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        do_trial = userdata.get('do-trial', 1)
        if do_trial not in (0, 1):
            context = {
                'success': False,
                'message': 'do-trial value must be either 0 or 1'
            }
            logError(logger, request, context['message'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # If user has had a prior subscription, do_trial must be 0
        if do_trial:
            last_subscription = UserSubscription.objects.getLatestSubscription(request.user)
            if last_subscription:
                context = {
                    'success': False,
                    'message': 'Renewing subscription is not permitted a trial period.'
                }
                message = context['message'] + ' last_subscription id: {0}'.format(last_subscription.pk)
                logError(logger, request, message)
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # plan pk (primary_key of plan in db)
        planPk = userdata.get('plan-id', None)
        if not planPk:
            context = {
                'success': False,
                'message': 'Plan Id is required (pk)'
            }
            logError(logger, request, context['message'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        try:
            plan = SubscriptionPlan.objects.get(pk=planPk)
        except ObjectDoesNotExist:
            context = {
                'success': False,
                'message': 'Invalid Plan Id (pk)'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        subs_params = {
            'plan_id': plan.planId # planId must exist in BT Control Panel
        }
        if not do_trial:
            subs_params['trial_duration'] = 0  # subscription starts immediately
        # get local customer object and braintree customer
        try:
            customer = Customer.objects.get(user=request.user)
            bc = Customer.objects.findBtCustomer(customer)
        except Customer.DoesNotExist:
            context = {
                'success': False,
                'message': 'Local Customer object not found for user.'
            }
            logError(logger, request, context['message'])
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        except braintree.exceptions.not_found_error.NotFoundError:
            context = {
                'success': False,
                'message': 'BT Customer object not found.'
            }
            message = context['message'] + ' customerId: {0}'.format(customer.customerId)
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)

        if payment_nonce:
            # We would only create a new subscription when there was no previous subscription or everything was cancelled
            # so should be safe to make sure that user has no or just one payment method (can't be many).
            Customer.objects.makeSureNoMultipleMethods(customer)

            # First we need to update the Customer Vault to get a token
            try:
                result = Customer.objects.addOrUpdatePaymentMethod(customer, payment_nonce)
            except ValueError, e:
                context = {
                    'success': False,
                    'message': str(e)
                }
                logException(logger, request, 'NewSubscription ValueError')
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            if not result.is_success:
                context = {
                    'success': False,
                    'message': 'Customer vault update failed.'
                }
                message = 'NewSubscription: Customer vault update failed. Result message: {0.message}'.format(result)
                logError(logger, request, message)
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
            bc2 = Customer.objects.findBtCustomer(customer)
            tokens = [m.token for m in bc2.payment_methods]
            payment_token = tokens[0]
        # Update params for subscription
        subs_params['payment_method_token'] = payment_token
        # Create the subscription and transaction record
        with transaction.atomic():
            result, user_subs = UserSubscription.objects.createBtSubscription(request.user, plan, subs_params)
        context = {'success': result.is_success}
        if not result.is_success:
            context['message'] = 'Create Subscription failed.'
            message = 'NewSubscription: Create Subscription failed. Result message: {0.message}'.format(result)
            logError(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context['subscriptionId'] = user_subs.subscriptionId
            context['bt_status'] = user_subs.status
            context['display_status'] = user_subs.display_status
            context['billingStartDate'] = user_subs.billingStartDate
            context['billingEndDate'] = user_subs.billingEndDate
            logInfo(logger, request, 'NewSubscription: complete for subscriptionId={0.subscriptionId}'.format(user_subs))
        return Response(context, status=status.HTTP_201_CREATED)


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
    This view expects a JSON object from the POST:
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
        if user_subs.display_status != UserSubscription.UI_ACTIVE_CANCELED:
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


#
# testing only
#
@method_decorator(login_required, name='dispatch')
class TestForm(generic.TemplateView):
    template_name = os.path.join(TPL_DIR, 'payment_test_form.html')
    def get_context_data(self, **kwargs):
        context = super(TestForm, self).get_context_data(**kwargs)
        context['token'] = braintree.ClientToken.generate()
        return context
