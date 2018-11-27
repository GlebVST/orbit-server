from users.models import *
from django.db import transaction

def main():
    """To be run in shell to rename SubscriptionPlans.
    >>> from scripts import renamePlus2BasicPlans as s
    >>> s.main()
    Rename BT Plus plans to Basic and planId: change plus to basic
    Add 7 day trial period
    No firstyear discount
    No downgrade_plan (Standard will become legacy)
    Note: remember to re-sync plans with Braintree Control Panel
    """
    plan_type = SubscriptionPlanType.objects.get(name=SubscriptionPlanType.BRAINTREE)
    plus_plans = SubscriptionPlan.objects.filter(plan_type=plan_type, display_name='Plus').order_by('name')
    basicPlansDict = {}
    for p in plus_plans:
        p.display_name = 'Basic'
        p.name = p.name.replace('Plus','Basic')
        p.planId = p.planId.replace('plus','basic')
        p.discountPrice = p.price # no firstyear discount
        p.trialDays = 7
        p.downgrade_plan = None
        p.save()
        basicPlansDict[p.name] = p
        print('Updated plan {0.planId}'.format(p))
    # rename free plans
    pt_free = SubscriptionPlanType.objects.get(name=SubscriptionPlanType.FREE_INDIVIDUAL)
    free_plans = SubscriptionPlan.objects.filter(plan_type=pt_free).order_by('name')
    for p in free_plans:
        p.display_name = 'Basic'
        p.name = p.name.replace('Standard','Basic')
        basic_name = p.name.replace('Free ', '')
        basic_plan = basicPlansDict.get(basic_name, None)
        if basic_plan:
            p.upgrade_plan = basic_plan
        else:
            print('Could not find upgrade_plan for: {0}'.format(basic_name))
        p.save()
        print('Updated free plan {0.planId}'.format(p))
