import logging
from datetime import timedelta
from smtplib import SMTPException
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from users.models import BrowserCme, Customer, UserSubscription, SubscriptionEmail, SubscriptionPlanType
from users.emailutils import sendRenewalReminderEmail, sendCancelReminderEmail

logger = logging.getLogger('mgmt.remail')
CUTOFF = 30

class Command(BaseCommand):
    help = "Find all active susbcriptions within CUTOFF days of billingEndDate and send out reminder email."

    def handle(self, *args, **options):
        # calculate once (used for all emails in this executation) the total BrowserCme credits earned
        extra_data = {
            'totalCredits': int(BrowserCme.objects.totalCredits())
        }
        now = timezone.now()
        cutoffDate = now + timedelta(days=CUTOFF)
        f_status = (
                UserSubscription.UI_ACTIVE,
                UserSubscription.UI_ACTIVE_CANCELED,
                #UserSubscription.UI_ACTIVE_DOWNGRADE, # TODO: once we have appropriate email message for this case
            )
        qset = UserSubscription.objects.select_related('plan', 'plan__plan_type').filter(
            plan__plan_type=SubscriptionPlanType.BRAINTREE,
            display_status__in=f_status,
            billingEndDate__lte=cutoffDate
            ).order_by('billingEndDate')
        for m in qset:
            user = m.user
            subs_email, created = SubscriptionEmail.objects.getOrCreate(m)
            if not subs_email.remind_renew_sent:
                paymentMethods = Customer.objects.getPaymentMethods(user.customer)
                pm = paymentMethods[0]
                emailFunc = None
                try:
                    if m.status == UserSubscription.UI_ACTIVE_CANCELED:
                        emailFunc = sendCancelReminderEmail
                    #elif m.status == UserSubscription.UI_ACTIVE_DOWNGRADE:
                    #    emailFunc = sendDowngradeReminderEmail
                    else:
                        emailFunc = sendRenewalReminderEmail
                    if emailFunc:
                        emailFunc(m, pm, extra_data)
                except SMTPException as e:
                    logger.exception('Reminder email to {0.email} failed.'.format(user))
                else:
                    subs_email.remind_renew_sent = True
                    subs_email.save()
                    logger.info('Reminder email to {0.email} sent.'.format(user))
