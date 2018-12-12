import logging
from users.models import UserSubscription, UserCmeCredit
from dateutil.relativedelta import *
from django.utils import timezone
from django.core.management.base import BaseCommand
logger = logging.getLogger('mgmt.checkentsubs')

# This method should be run to update enterprise user plan credits on their period expiry (like every year)
class Command(BaseCommand):
    help = "Check enterprise subscriptions daily and switch to a next plan period if needed (with resetting plan_credits)"

    def handle(self, *args, **options):
        subscriptions = UserSubscription.objects.select_related('plan').filter(
            plan__plan_type__name='Enterprise'
        ).exclude(status=UserSubscription.CANCELED)
        logger.debug("Need to check {0} Enterprise subscriptions for period expiry".format(subscriptions.count()))
        for subs in subscriptions:
            plan = subs.plan
            # do not care about unlimited cme enterprise plans (if there would be any)
            if not plan.isUnlimitedCme() :
                user = subs.user
                next_period_start = subs.billingStartDate + relativedelta(months=plan.billingCycleMonths)
                if timezone.now() >= next_period_start:
                    prev_period_start = subs.billingStartDate
                    # only change a start date here as end date would be far in the future for enterprise subs
                    subs.billingStartDate = next_period_start
                    subs.save()
                    try:
                        existing_user_credit = UserCmeCredit.objects.get(user=user)
                    except UserCmeCredit.DoesNotExist:
                        # doubt it would ever happen given UserCmeCredit record get created together with a new subscription
                        logger.warn("Somehow user {0.id} got UserCmeCredit entry missing for enterprise subscription {1.id}".format(user, subs))
                    else:
                        logger.debug("Reset CME plan_credits for enterprise subscription user {0.id} (started {1}): {2} => {3}".format(user, prev_period_start, existing_user_credit.plan_credits, plan.maxCmeYear))
                        existing_user_credit.plan_credits = plan.maxCmeYear
                        existing_user_credit.save()


        logger.debug("Completed enterprise subscriptions check")