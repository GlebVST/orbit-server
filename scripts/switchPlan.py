from django.db import transaction
from users.models import *
from datetime import datetime
import pytz

def switchPlan(old_subs, newPlan):
    payment_methods = Customer.objects.getPaymentMethods(old_subs.user.customer)
    payment_method = payment_methods[0]
    expiry_dt = Customer.objects.getDateFromExpiry(payment_method['expiry'])
    now = timezone.now()
    if expiry_dt < now:
        print('switchPlan payment_method already expired: {expiry}'.format(payment_method))
        return False
    payment_token = payment_method['token']
    in_trial = old_subs.display_status == UserSubscription.UI_TRIAL
    result = UserSubscription.objects.terminalCancelBtSubscription(old_subs)
    if not result.is_success:
        print('terminalCancelBtSubscription failed for {0}'.format(old_subs))
        return False
    old_subs.display_status = UserSubscription.UI_EXPIRED
    old_subs.save()
    subs_params = {'plan_id':newPlan.planId, 'payment_method_token':payment_token}
    if not in_trial:
        subs_params['trial_duration'] = 0 # subscription starts immediately
    with transaction.atomic():
        result, user_subs = UserSubscription.objects.createBtSubscription(old_subs.user, newPlan, subs_params)
    return result.is_success
