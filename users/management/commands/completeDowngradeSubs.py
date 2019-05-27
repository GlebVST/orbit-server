import logging
from datetime import timedelta
from smtplib import SMTPException
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from users.models import Customer, UserSubscription, SubscriptionEmail
from users.emailutils import sendCardExpiredAlertEmail

logger = logging.getLogger('mgmt.downg')


class Command(BaseCommand):
    help = "Finds all UI_ACTIVE_DOWNGRADE susbcriptions at cutoffDate and start new subscription."""

    def handle(self, *args, **options):
        now = timezone.now()
        cutoffDate = now + timedelta(days=1)
        qset = UserSubscription.objects.filter(
            status=UserSubscription.UI_ACTIVE_DOWNGRADE,
            billingEndDate__lte=cutoffDate
            ).order_by('billingEndDate')
        for m in qset:
            user = m.user
            paymentMethods = Customer.objects.getPaymentMethods(user.customer)
            pm = paymentMethods[0]
            if pm['expired']:
                subs_email, created = SubscriptionEmail.objects.getOrCreate(m)
                if not subs_email.expire_alert_sent:
                    try:
                        sendCardExpiredAlertEmail(m, pm)
                    except SMTPException as e:
                        logger.exception('Card expiry alert email to {0.email} failed'.format(user))
                    else:
                        subs_email.expire_alert_sent = True
                        subs_email.save()
                        logger.info('Card expiry alert email to {0.email} sent.'.format(user))
                continue
            paymentToken = pm['token']
            if not m.next_plan:
                logger.error('completeDowngradeSubs: next_plan not set on UserSubscription {0.pk}|{0}'.format(m))
                continue
            (result, new_user_subs) = UserSubscription.objects.completeDowngrade(m, paymentToken)
            if result.is_success:
                logger.info('Downgrade complete for User {0.email} with new user_subs: {1}'.format(user, new_user_subs))
            else:
                logger.error('completeDowngrade failed for user {0.email}'.format(user))
