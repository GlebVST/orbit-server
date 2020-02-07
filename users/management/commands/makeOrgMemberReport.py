import logging
from datetime import datetime, timedelta
import pytz
from smtplib import SMTPException
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db.models import Subquery
from django.template.loader import get_template
from django.utils import timezone
from users.models import User, Profile, Organization, OrgMember
from users.emailutils import makeCsvForAttachment, sendEmailWithAttachment

logger = logging.getLogger('mgmt.orgmr')

class Command(BaseCommand):
    help = "Generate report of the enterprise members (NPI, Name, Email, Status) for the specified Org."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('orgcode',
            help='Organization joincode. One word (no whitespace). Must already exist in the db.')

    def handle(self, *args, **options):
        # validate options
        try:
            org = Organization.objects.get(joinCode__iexact=options['orgcode'])
        except Organization.DoesNotExist:
            self.stderr.write('Invalid Organization joinCode: {0} (does not exist)'.format(options['orgcode']))
            return
        # get member list
        fieldnames, results = OrgMember.objects.listEnterpriseMembersOfOrg(org) # list of dicts
        # write results to contentfile
        cf = makeCsvForAttachment(fieldnames, results)
        # create EmailMessage
        from_email = settings.EMAIL_FROM
        cc_emails = []
        if settings.ENV_TYPE == settings.ENV_PROD:
            to_emails = [settings.FOUNDER_EMAIL,]
            bcc_emails = [settings.DEV_EMAILS[0],]
        else:
            # internal testing
            to_emails = [settings.DEV_EMAILS[0],]
            bcc_emails = []
        reportDate = timezone.now()
        subject = "Orbit Member List for {0.name} ({1:%b/%d/%Y})".format(org, reportDate)
        reportFileName = 'orbit-providers-{0:%b%d%Y}.csv'.format(reportDate)
        # data for context
        ctx = {
            'organization': org,
            'reportDate': reportDate,
        }
        message = get_template('email/org_memberlist_report.html').render(ctx)
        try:
            sendEmailWithAttachment(subject,
                message,
                cf,
                reportFileName,
                from_email,
                to_emails, cc_emails, bcc_emails)
        except SMTPException as e:
            logger.exception('makeOrgMemberReport send email failed')
        else:
            logger.info('makeOrgMemberReport done')
            self.stdout.write('makeOrgMemberReport done')
