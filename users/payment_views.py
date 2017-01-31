import os
import braintree
import json
import datetime
from datetime import timedelta
from pprint import pprint
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import generic
from django.views.decorators.csrf import csrf_exempt
from oauth2_provider.ext.rest_framework import TokenHasReadWriteScope, TokenHasScope
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser
# proj
from common.viewutils import JsonResponseMixin
# app
from .models import *
import logging

TPL_DIR = 'users'

logger = logging.getLogger(__name__)

# https://developers.braintreepayments.com/start/hello-server/python
class GetToken(JsonResponseMixin, APIView):
    """
    This endpoint returns a Braintree Client Token.

    """
    def get(self, request, *args, **kwargs):
        context = {
            'token': braintree.ClientToken.generate()
        }
        return self.render_to_json_response(context)

class GetPaymentMethods(JsonResponseMixin, APIView):
    """
    This endpoint returns a list of existing payment methods from the Braintree Customer (if any).

    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def get(self, request, *args, **kwargs):
        user = request.user
        local_customer = Customer.objects.get(user=user)
        btree_customer = braintree.Customer.find(str(local_customer.customerId))
        results = [{ "token": m.token, "number": m.masked_number, "type": m.card_type, "expiry": m.expiration_date } for m in btree_customer.payment_methods]
        logger.debug("Customer {} payment methods: {}".format(local_customer, results))
        return self.render_to_json_response(results)

class Checkout(JsonResponseMixin, APIView):
    """
    This view expects a JSON object from the POST with Braintree transaction details.

    Example JSON when using existing customer payment method with token obtained from BT Vault:
    {"point-purchase-option-id":1,"payment-method-token":"5wfrrp"}

    Example JSON when using a new payment method with a Nonce prepared on client:
    {"point-purchase-option-id":1,"payment-method-nonce":"cd36493e-f883-48c2-aef8-3789ee3569a9"}

    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, *args, **kwargs):
        context = {}
        userdata = request.data
        payment_nonce = userdata.get('payment-method-nonce', None)
        payment_token = userdata.get('payment-method-token', None)
        # some basic validation for incoming parameters
        if not payment_nonce and not payment_token:
            context = {
                'success': False,
                'error_message': 'Payment Nonce or Method Token is required'
            }
            return self.render_to_json_response(context, status_code=400)
        ppoId = userdata.get('point-purchase-option-id', None)
        if not ppoId:
            context = {
                'success': False,
                'error_message': 'Point Purchase Option Id is required'
            }
            return self.render_to_json_response(context, status_code=400)
        # get purchase option to know the transaction amount and points for assignment
        try:
            ppo = PointPurchaseOption.objects.get(pk=ppoId)
        except ObjectDoesNotExist:
            context = {
                'success': False,
                'error_message': 'Invalid Point Purchase Option Id'
            }
            return self.render_to_json_response(context, status_code=400)

        # get customer object from database
        customer = Customer.objects.get(user=request.user)

        # prepare transaction details depending on payment method
        transaction_params = {
            "amount": str(ppo.price),
            "options": {
                "submit_for_settlement": True
            }
        }
        if payment_token:
            # paying with previously used method obtained from the UI via payment_method_token
            transaction_params['payment_method_token'] = payment_token
        else:
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
        logger.debug("Braintree transaction response: {}".format(result))

        success = result.is_success # bool
        context['success'] = success
        if success:
            status = result.transaction.status
            logger.info("Customer {} Braintree transaction status: {}".format(customer, status))
            context['status'] = status
            context['transactionid'] = result.transaction.id
            # update database using atomic transaction
            with transaction.atomic():
                PointTransaction.objects.create(
                    customer=customer,
                    points=ppo.points,
                    pricePaid=ppo.price,
                    transactionId=result.transaction.id
                )
                # update points balance
                customer.balance += ppo.points
                customer.save()
            context['balance'] = str(customer.balance)
            return self.render_to_json_response(context)
        else:
            if hasattr(result, 'transaction') and result.transaction is not None:
                trans = result.transaction
                status = trans.status
                logger.info("Transaction status: {}".format(status))
                context['status'] = status
                if status == 'processor_declined':
                    context['processor_response_code'] = trans.processor_response_code
                    context['processor_response_text'] = trans.processor_response_text
                    # additional bank-specific info
                    context['additional_processor_response'] = trans.additional_processor_response
                elif status == 'settlement_declined':
                    context['processor_settlement_response_code'] = trans.processor_response_code
                    context['processor_settlement_response_text'] = trans.processor_response_text
                elif status == 'gateway_rejected':
                    context['gateway_rejection_reason'] = trans.gateway_rejection_reason
            else:
                # validation error
                status_code = 400
                context['status'] = 'validation_error'
                context['validation_errors'] = []
                for error in result.errors.deep_errors:
                    context['validation_errors'].append({
                        'attribute': error.attribute,
                        'code': error.code,
                        'message': error.message
                    })
            return self.render_to_json_response(context, status_code)

class UpdatePaymentToken(JsonResponseMixin, APIView):
    """
    This view allows the customer to update an existing payment
    token with a new nonce (e.g. to update an expired card)
    Reference: https://developers.braintreepayments.com/reference/request/customer/update/python#examples
    Example JSON:
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
        if not payment_nonce or not payment_token:
            context = {
                'success': False,
                'error_message': 'Payment Nonce and Payment Token are both required.'
            }
            return self.render_to_json_response(context, status_code=400)
        # get customer object from database
        try:
            customer = Customer.objects.get(user=request.user)
        except Customer.DoesNotExist:
            context = {
                'success': False,
                'error_message': 'Customer object not found.'
            }
            return self.render_to_json_response(context, status_code=400)
        # Update Customer
        result = braintree.Customer.update(str(customer.customerId), {
            "credit_card": {
                "payment_method_nonce": payment_nonce,
                "options": {
                    "update_existing_token": payment_token
                }
            }
        })
        context = {
            'success': result.is_success
        }
        return self.render_to_json_response(context)


class NewSubscription(JsonResponseMixin, APIView):
    """
    This view expects a JSON object from the POST with Braintree transaction details.
    Example JSON when using existing customer payment method with token obtained from BT Vault:
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
                'error_message': 'User has an existing Subscription that must be canceled first.'
            }
            return self.render_to_json_response(context, status_code=400)
        userdata = request.data
        # some basic validation for incoming parameters
        payment_nonce = userdata.get('payment-method-nonce', None)
        payment_token = userdata.get('payment-method-token', None)
        if not payment_nonce and not payment_token:
            context = {
                'success': False,
                'error_message': 'Payment Nonce or Method Token is required'
            }
            return self.render_to_json_response(context, status_code=400)
        do_trial = userdata.get('do-trial', 1)
        if do_trial not in (0, 1):
            context = {
                'success': False,
                'error_message': 'do-trial value must be either 0 or 1'
            }
            return self.render_to_json_response(context, status_code=400)
        # plan pk (primary_key of plan in db)
        planPk = userdata.get('plan-id', None)
        if not planPk:
            context = {
                'success': False,
                'error_message': 'Plan Id is required (pk)'
            }
            return self.render_to_json_response(context, status_code=400)
        try:
            plan = SubscriptionPlan.objects.get(pk=planPk)
        except ObjectDoesNotExist:
            context = {
                'success': False,
                'error_message': 'Invalid Plan Id (pk)'
            }
            return self.render_to_json_response(context, status_code=400)
        subs_params = {
            'plan_id': plan.planId # planId must exist in Braintree Control Panel
        }
        if not do_trial:
            subs_params['trial_duration'] = 0  # subscription starts immediately
        # get customer object from database
        try:
            customer = Customer.objects.get(user=request.user)
        except Customer.DoesNotExist:
            context = {
                'success': False,
                'error_message': 'Customer object not found.'
            }
            return self.render_to_json_response(context, status_code=400)

        if payment_nonce:
            # First we need to update the Customer in the Vault to get a token
            # Fetch existing list of tokens
            bc1 = braintree.Customer.find(str(customer.customerId))
            tokens1 = [m.token for m in bc1.payment_methods]

            # Now add new payment method
            result = braintree.Customer.update(str(customer.customerId), {
                "credit_card": {
                    "payment_method_nonce": payment_nonce
                }
            })
            if not result.is_success:
                context = {
                    'success': False,
                    'error_message': 'Customer vault update failed.'
                }
                return self.render_to_json_response(context, status_code=400)
            # Fetch list of tokens again
            bc2 = braintree.Customer.find(str(customer.customerId))
            tokens2 = [m.token for m in bc2.payment_methods]
            # Find the new token
            token_diff_set = set(tokens2) - set(tokens1)
            if len(token_diff_set):
                new_payment_token = token_diff_set.pop()
                # Update params for subscription
                subs_params['payment_method_token'] = new_payment_token
        else:
            # Update params for subscription
            subs_params['payment_method_token'] = payment_token
        # finally, create the subscription
        result, user_subs = UserSubscription.objects.createBtSubscription(plan, subs_params)
        context = {
            'success': result.is_success
        }
        if result.is_success:
            context['subscriptionId'] = user_subs.subscriptionId
            context['bt_status'] = user_subs.status
            context['display_status'] = user_subs.display_status
            context['billingStartDate'] = user_subs.billingStartDate
            context['billingEndDate'] = user_subs.billingEndDate
        return self.render_to_json_response(context)


class CancelSubscription(JsonResponseMixin, APIView):
    """
    This view expects a JSON object from the POST:
    {"subscription-id": braintree subscriptionid to cancel}
    If the subscription Id is valid, it will be canceled.
    https://developers.braintreepayments.com/reference/request/subscription/cancel/python
    Once canceled, a subscription cannot be reactivated.
    You would have to create a new subscription.
    You cannot cancel subscriptions that have already been canceled.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, *args, **kwargs):
        userdata = request.data
        subscriptionId = userdata.get('subscription-id', None)
        if not subscriptionId:
            context = {
                'success': False,
                'error_message': 'bt SubscriptionId is required'
            }
            return self.render_to_json_response(context, status_code=400)
        try:
            user_subs = UserSubscription.objects.get(
                user=request.user,
                subscriptionId=subscriptionId
            )
        except UserSubscription.DoesNotExist:
            context = {
                'success': False,
                'error_message': 'UserSubscription local object not found.'
            }
            return self.render_to_json_response(context, status_code=400)
        # check current status
        if user_subs.status != UserSubscription.ACTIVE or user_subs.status != UserSubscription.PENDING:
            context = {
                'success': False,
                'error_message': 'UserSubscription status is already: ' + user_subs.status
            }
            return self.render_to_json_response(context, status_code=400)
        # proceed with cancel
        try:
            result = UserSubscription.objects.cancelBtSubscription(user_subs)
        except braintree.exceptions.not_found_error.NotFoundError:
            context = {
                'success': False,
                'error_message': 'btSubscription not found.'
            }
            return self.render_to_json_response(context, status_code=400)
        else:
            if not result.is_success:
                context = {
                    'success': False,
                    'error_message': 'btSubscription cancel failed.'
                }
                return self.render_to_json_response(context, status_code=400)
            else:
                context = {
                    'success': True,
                    'bt_status': user_subs.status,
                    'display_status': user_subs.display_status
                }
                return self.render_to_json_response(context)

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
