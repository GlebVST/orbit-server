from users.models import *

BILLING_CYCLE_MONTHS=24
PRO_PRICE = 24.99*BILLING_CYCLE_MONTHS
def main():
    """Create new 2-year billingCycle Pro plans"""
    plan_type = SubscriptionPlanType.objects.get(name=SubscriptionPlanType.BRAINTREE)
    basic_plans = SubscriptionPlan.objects.select_related('upgrade_plan').filter(plan_type=plan_type, display_name='Basic').order_by('name')
    for p in basic_plans:
        if p.upgrade_plan and p.upgrade_plan.display_name == 'Pro':
            continue
        name = p.name.replace('Basic', 'Pro')
        pro_planId = SubscriptionPlan.objects.makePlanId(name)
        pro_plan = SubscriptionPlan.objects.create(
                planId=pro_planId,
                plan_type=p.plan_type,
                plan_key=p.plan_key,
                display_name='Pro',
                name=name,
                price=PRO_PRICE,
                discountPrice=PRO_PRICE,
                billingCycleMonths=BILLING_CYCLE_MONTHS,
                trialDays=0,
                maxCmeYear=p.maxCmeYear*2,
                downgrade_plan=p
            )
        p.upgrade_plan = pro_plan
        p.save(update_fields=('upgrade_plan',))
        print('{0.name} -> {1.name} {1.planId}'.format(p, pro_plan))
