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
# proj
from common.viewutils import JsonResponseMixin
# app
from .models import *

TPL_DIR = 'users'

# https://developers.braintreepayments.com/start/hello-server/python
class GetToken(JsonResponseMixin, generic.View):
    http_method_names = ['get',]

    def get(self, request, *args, **kwargs):
        context = {
            'token': braintree.ClientToken.generate()
        }
        return self.render_to_json_response(context)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required, name='dispatch')
class Checkout(JsonResponseMixin, generic.View):
    http_method_names = ['post',]
    def post(self, request, *args, **kwargs):
        context = {}
        userdata = self.request.POST.copy()
        print(userdata)
        nonce = userdata.get('payment-method-nonce', None)
        if not nonce:
            context = {
                'success': False,
                'error_message': 'Nonce is required'
            }
            return self.render_to_json_response(context, status_code=400)
        ppoId = userdata.get('point-purchase-option-id', None)
        if not ppoId:
            context = {
                'success': False,
                'error_message': 'Point Purchase Option Id is required'
            }
            return self.render_to_json_response(context, status_code=400)
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
        # https://developers.braintreepayments.com/reference/request/transaction/sale/python
        # https://developers.braintreepayments.com/reference/response/transaction/python#result-object
        result = braintree.Transaction.sale({
            "amount": str(ppo.price),
            "payment_method_nonce": nonce,
            "options": {
                "submit_for_settlement": True
            }
        })
        print(result)
        success = result.is_success # bool
        context['success'] = success
        if success:
            status = result.transaction.status
            print(status)
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
                    "payment_method_nonce": nonce
                }
            })
            context['customer_updated_success'] = result.is_success
            pprint(context)
            return self.render_to_json_response(context)
        else:
            if hasattr(result, 'transaction') and result.transaction is not None:
                trans = result.transaction
                status = trans.status
                print(status)
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
