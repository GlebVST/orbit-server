import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from users.models import UserSubscription, SubscriptionTransaction, InvitationDiscount

logger = logging.getLogger('mgmt.invite')


class Command(BaseCommand):
    help = "Get pending InvitationDiscounts. For each: check if invitee has begun Active subscription and if so update the InvitationDiscount, and possibly the inviter subscription."

    def handle(self, *args, **options):
        # pending InvitationDiscount: inviterDiscount is null
        qset = InvitationDiscount.objects.filter(inviterDiscount__isnull=True).order_by('created')
        for m in qset:
            inviter = m.inviter # User
            invitee = m.invitee # User
            inviter_subs = UserSubscription.objects.getLatestSubscription(inviter)
            if not inviter_subs:
                logger.info('Inviter {0} does not have a subscription yet.'.format(inviter))
                continue
            # terminal states don't have a next billingCycle
            if (inviter_subs.status == UserSubscription.CANCELED) or (inviter_subs.status == UserSubscription.EXPIRED):
                logger.info('Inviter {0} has terminal subscription status: {1}. Cannot apply discount.'.format(inviter, inviter_subs.status))
                continue
            # If inviter is still in Trial, need to wait until they switch to Active before applying any discounts
            if (inviter_subs.display_status == UserSubscription.UI_TRIAL):
                logger.info('Inviter {0} is still in Trial. Cannot apply discount yet.'.format(inviter))
                continue
            invitee_subs = UserSubscription.objects.getLatestSubscription(invitee)
            if not invitee_subs:
                logger.info('Invitee {0} does not have a subscription yet.'.format(invitee))
                continue
            # Check if invitee has begin active subscription
            if invitee_subs.status == UserSubscription.ACTIVE and SubscriptionTransaction.objects.filter(subscription=invitee_subs).exists():
                # Can apply inviter discount to inviter
                #print('Calling updateSubscriptionForInviterDiscount for {0}'.format(inviter_subs))
                invDisc, is_saved = UserSubscription.objects.updateSubscriptionForInviterDiscount(inviter_subs, m)
                if is_saved:
                    logger.info('InvitationDiscount complete for Inviter {0} to Invitee {1}.'.format(inviter, invitee))
                    #print('InvitationDiscount complete for Inviter {0} to Invitee {1}.'.format(inviter, invitee))
