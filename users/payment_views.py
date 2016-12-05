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
from rest_framework.views import APIView
from django.views.decorators.csrf import csrf_exempt
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
    def get(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated():
            context = {
                'success': False,
                'error_message': 'User not authenticated'
            }
            return self.render_to_json_response(context, status_code=401)

        local_customer = Customer.objects.get(user=user)
        btree_customer = braintree.Customer.find(str(local_customer.customerId))
        results = [{ "token": m.token, "number": m.masked_number, "type": m.card_type, "expiry": m.expiration_date } for m in btree_customer.payment_methods]
        logger.debug("Customer {} payment methods: {}".format(local_customer, results))
        return self.render_to_json_response(results)

# @method_decorator(csrf_exempt, name='dispatch')
# @method_decorator(login_required, name='dispatch')
class Checkout(JsonResponseMixin, APIView):
    """
    This view expects a JSON object from the POST with Braintree transaction details.

    Example JSON when using existing customer payment method with token obtained from BT Vault:
    {"point-purchase-option-id":1,"payment-method-token":"5wfrrp"}

    Example JSON when using a new payment method with a Nonce prepared on client:
    {"point-purchase-option-id":1,"payment-method-nonce":"cd36493e-f883-48c2-aef8-3789ee3569a9"}

    """
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
            # update braintree customer information: add payment method
            result = braintree.Customer.update(str(customer.customerId), {
                "credit_card": {
                    "payment_method_nonce": payment_nonce
                }
            })
            context['customer_updated_success'] = result.is_success
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
