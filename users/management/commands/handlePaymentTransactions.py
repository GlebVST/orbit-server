import logging
from smtplib import SMTPException
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from users.models import Profile, SubscriptionPlan, UserSubscription, SubscriptionTransaction
from users.emailutils import sendReceiptEmail, sendPaymentFailureEmail

logger = logging.getLogger('mgmt.rcpt')


class Command(BaseCommand):
    help = "Updates the latest UserSubscription and its associated transactions, and send receipt emails"""

    def handle(self, *args, **options):
        profiles = Profile.objects.all().order_by('-created')
        for profile in profiles:
            user = profile.user
            user_subs = UserSubscription.objects.getLatestSubscription(user)
            if not user_subs:
                continue
            # terminal states that don't need to check for updates
            if (user_subs.status == UserSubscription.CANCELED) or (user_subs.status == UserSubscription.EXPIRED):
                continue
            bt_subs = UserSubscription.objects.findBtSubscription(user_subs.subscriptionId)
            if user_subs.status != bt_subs.status or user_subs.billingCycle != bt_subs.current_billing_cycle:
                logger.info('Updating subscriptionId: {0.subscriptionId}'.format(user_subs))
                UserSubscription.objects.updateSubscriptionFromBt(user_subs, bt_subs)
            # create and/or update transactions for this user_subs
            created, updated = SubscriptionTransaction.objects.updateTransactionsFromBtSubs(user_subs, bt_subs)
            self.stdout.write('UserSubs {0.subscriptionId} num_t_created: {1} num_t_updated: {2}'.format(user_subs, len(created), len(updated)))
            for t_pk in created:
                m = SubscriptionTransaction.objects.get(pk=t_pk)
                if m.canSendReceipt():
                    try:
                        sendReceiptEmail(user, user_subs, m)
                    except SMTPException as e:
                        logger.exception('Email receipt to {0.email} failed'.format(user))
                    else:
                        m.receipt_sent = True
                        m.save()
                        logger.info('Email receipt to {0.email} for transactionId {1.transactionId}'.format(user, m))
                elif m.canSendFailureAlert():
                    try:
                        sendPaymentFailureEmail(user, m)
                    except:
                        logger.exception('Email payment_failure to {0.email} failed'.format(user))
                    else:
                        m.failure_alert_sent = True
                        m.save()
                        logger.info('Email payment_failure to {0.email} for transactionId {1.transactionId}'.format(user, m))
            for t_pk in updated:
                m = SubscriptionTransaction.objects.get(pk=t_pk)
                if not m.receipt_sent and m.canSendReceipt():
                    try:
                        sendReceiptEmail(user, user_subs, m)
                    except SMTPException as e:
                        logger.exception('Email receipt to {0.email} failed'.format(user))
                    else:
                        m.receipt_sent = True
                        m.save()
                        logger.info('Email receipt to {0.email} for transactionId {1.transactionId}'.format(user, m))
                elif not m.failure_alert_sent and m.canSendFailureAlert():
                    try:
                        sendPaymentFailureEmail(user, m)
                    except:
                        logger.exception('Email payment_failure to {0.email} failed'.format(user))
                    else:
                        m.failure_alert_sent = True
                        m.save()
                        logger.info('Email payment_failure to {0.email} for transactionId {1.transactionId}'.format(user, m))
            # finally, send emails for all settled transactions whose receipt_sent is False
            qset = user_subs.transactions.filter(receipt_sent=False, status=SubscriptionTransaction.SETTLED)
            for m in qset:
                try:
                    sendReceiptEmail(user, user_subs, m)
                except SMTPException as e:
                    logger.exception('Email receipt to {0.email} failed'.format(user))
                else:
                    m.receipt_sent = True
                    m.save()
                    logger.info('Email receipt to {0.email} for transactionId {1.transactionId}'.format(user, m))
