import logging
from users.models import UserSubscription, BrowserCme, UserCmeCredit
from django.db.models import Sum
from django.core.management.base import BaseCommand
logger = logging.getLogger('mgmt.setcmecred')

class Command(BaseCommand):
    help = "Calculate amount of redeemed CME credits for all users and update corresponding value on UserCmeCredit record"

    def handle(self, *args, **options):
        subscriptions = UserSubscription.objects.select_related('plan').all().exclude(status=UserSubscription.CANCELED)
        logger.debug("Need to setup {0} user CME credit records".format(subscriptions.count()))
        for subs in subscriptions:
            plan = subs.plan
            user = subs.user
            qs = BrowserCme.objects.select_related('entry').filter(
                entry__user=user,
                entry__activityDate__year=subs.billingStartDate.year,
                entry__valid=True
            ).aggregate(cme_total=Sum('credits'))
            redeemedTotal = qs['cme_total']
            if not redeemedTotal:
                redeemedTotal = 0

            planCredits = 0
            if plan.isUnlimitedCme() :
                planCredits = UserSubscription.MAX_FREE_SUBSCRIPTION_CME
            elif plan.maxCmeYear > redeemedTotal:
                planCredits = plan.maxCmeYear - redeemedTotal

            existingUserCredit = self.getExistingUserCredit(user)
            if not existingUserCredit:
                logger.debug("Setup {0} plan_credits for user {1.id}, already redeemed {2} out of max {3}".format(planCredits, user, redeemedTotal, (plan.maxCmeYear if plan.maxCmeYear else "Unlimited" )))
                UserCmeCredit.objects.create(
                    user=user,
                    plan_credits=planCredits,
                    boost_credits=0
                )
            else:
                logger.debug("User {0.id} already have cme credit entry, so far redeemed {1} out of max {2}".format(user, redeemedTotal, (plan.maxCmeYear if plan.maxCmeYear else "Unlimited" )))
        logger.debug("Completed user CME credit setup")

    def getExistingUserCredit(self, user):
        try:
            return UserCmeCredit.objects.get(user=user)
        except UserCmeCredit.DoesNotExist:
            return None
