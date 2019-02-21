import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from users.models import User, UserSubscription

logger = logging.getLogger('mgmt.cbtsub')

class Command(BaseCommand):
    help = "Cancel Braintree subscription for a user. This is a TERMINAL action."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('email',
                help='User email. Must already exist in the db.')

    def handle(self, *args, **options):
        try:
            user = User.objects.get(email__iexact=options['email'])
        except User.DoesNotExist:
            self.stderr.write('Invalid user email: does not exist')
            return
        user_subs = UserSubscription.objects.getLatestSubscription(user)

        if not user_subs:
            self.stderr.write('User {0} has no UserSubscription. Exiting.'.format(user))
            return
        if not user_subs.plan.isPaid():
            self.stderr.write('User {0} does not have a paid UserSubscription. Exiting.'.format(user))
            return
        # check if user_subs is already in a terminal state
        if (user_subs.status == UserSubscription.CANCELED) or (user_subs.status == UserSubscription.EXPIRED):
            self.stderr.write('UserSubscription for {0.user} is already in a terminal state for subscriptionId: {0.subscriptionId}/{0.status}. Exiting.'.format(user_subs))
            return
        # cancel bt subs
        result = UserSubscription.objects.terminalCancelBtSubscription(user_subs)
        if result.is_success:
            msg = "cancelBtSubscription completed for {0.user} subscriptionId: {0.subscriptionId}".format(user_subs)
            logger.info(msg)
            self.stdout.write(msg)
        else:
            logger.warning('cancelBtSubscription failed for {0.user} subscriptionId: {0.subscriptionId}'.format(user_subs))
            self.sterr.write(result)
