import logging
import os
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from users.models import User, SubscriptionPlanType, SubscriptionPlan, UserSubscription

logger = logging.getLogger('mgmt.swplan')

class Command(BaseCommand):
    help = "End current subscription and start new subscription for the given user and new planId. This does not handle refunds or extra charges which should be done using the Braintree Control Panel."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('user_email', help='Email address of the user')
        parser.add_argument('new_planId', help='planId of the NEW plan to switch user to')

    def handle(self, *args, **options):
        user_email = options['user_email']
        new_planId = options['new_planId']
        pt_bt = SubscriptionPlanType.objects.get(name=SubscriptionPlanType.BRAINTREE)
        # check user
        if not User.objects.filter(email=user_email).exists():
            raise ValueError('Invalid user_email. User does not exist.')
            return
        user = User.objects.get(email=user_email)
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        if user_subs.plan.plan_type != pt_bt:
            raise ValueError("Error. Current user subscription is not on a Braintree plan: {0.plan}".format(user_subs))
            return
        # check planId
        if not SubscriptionPlan.objects.filter(planId=new_planId, plan_type=pt_bt).exists():
            raise ValueError('Invalid planId. Could not find a Braintree plan with this planId.')
            return
        new_plan = SubscriptionPlan.objects.get(planId=new_planId, plan_type=pt_bt)
        # check if nothing to do
        if user_subs.plan == new_plan:
            raise ValueError('Error. Current user subscription {0.subscriptionId} is already on plan: {0.plan}. Exiting.'.format(user_subs))
            return
        msg = "Switch User {0} from {1.plan} to {2}. Type y to continue: ".format(user, user_subs, new_plan)
        val = input(msg)
        if val.lower() != 'y':
            self.stdout.write('Exiting')
            return
        new_user_subs = UserSubscription.objects.switchPlanNoCharge(user_subs, new_plan)
        if new_user_subs:
            msg = "Successfully ended old subscription: {0.subscriptionId}. Created new subscription: {1.subscriptionId} on plan {1.plan}".format(user_subs, new_user_subs)
            logger.info(msg)
            self.stdout.write(msg)
        else:
            msg = "SwitchPlanNoCharge failed. Check log files for errors."
            self.stderr.write(msg)
            logger.warning(msg)
        self.stdout.write('Done')
