from users.models import *
from django.db import transaction

def main():
    """To be run in shell to rename SubscriptionPlans.
    >>> from scripts import renamePlus2BasicPlans as s
    >>> s.main()
    Rename BT Plus plans to Basic
    Add 7 day trial period
    No firstyear discount
    No downgrade_plan (Standard will become legacy)
    planId values remain as is (must be in sync with Braintree)
    """
    plan_type = SubscriptionPlanType.objects.get(name=SubscriptionPlanType.BRAINTREE)
    plus_plans = SubscriptionPlan.objects.filter(plan_type=plan_type, display_name='Plus').order_by('name')
        for p in plus_plans:
            p.display_name = 'Basic'
            p.name = p.name.replace('Plus','Basic')
            p.discountPrice = p.price # no firstyear discount
            p.trialDays = 7
            p.downgrade_plan = None
            p.save()
            print('Updated plan {0.planId}'.format(p))
    # rename free plans
    pt_free = SubscriptionPlanType.objects.get(name=SubscriptionPlanType.FREE_INDIVIDUAL)
    free_plans = SubscriptionPlan.objects.filter(plan_type=pt_free).order_by('name')
    for p in free_plans:
        p.display_name = 'Basic'
        p.name = p.name.replace('Standard','Basic')
        p.save()
        print('Updated free plan {0.planId}'.format(p))
