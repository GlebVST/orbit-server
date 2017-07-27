import logging
from datetime import timedelta
from smtplib import SMTPException
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from users.models import Profile, UserSubscription
from users.emailutils import sendNewUserReportEmail

logger = logging.getLogger('mgmt.newuser')


class Command(BaseCommand):
    help = "Finds the list of new users created in the past 24 hours and sends an email report to SALES_EMAIL"""

    def handle(self, *args, **options):
        now = timezone.now()
        cutoff = now - timedelta(days=1)
        profiles = Profile.objects.filter(created__gte=cutoff).order_by('created')
        email_to = settings.SALES_EMAIL
        if profiles.count():
            try:
                sendNewUserReportEmail(profiles, email_to)
            except SMTPException as e:
                logger.exception('New User Report Email to {0} failed'.format(email_to))
            else:
                logger.info('New User Report Email to {0} sent.'.format(email_to))

