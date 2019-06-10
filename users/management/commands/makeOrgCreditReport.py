import logging
from datetime import datetime, timedelta
from operator import itemgetter
from smtplib import SMTPException
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.template.loader import get_template
from django.utils import timezone
from users.models import User, OrbitCmeOffer, Organization, OrgMember
from users.emailutils import makeCsvForAttachment, sendEmailWithAttachment

logger = logging.getLogger('mgmt.orgecr')

# Accepted date format for command-line arguments startdate, enddate
outputFields = (
    'NPINumber',
    'First Name',
    'Last Name',
    'Credits',
    'Status',
)

class Command(BaseCommand):
    help = "Generate Credits Earned summary report for providers of the specified Org from org startDate to present date."

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

        now = timezone.now()
        startDate = org.creditStartDate
        endDate = now + timedelta(days=1)
        # omit pending members since they have not joined yet, and omit admin users
        orgmembers = OrgMember.objects \
                .select_related('user__profile') \
                .filter(organization=org, pending=False, is_admin=False)
        data = []
        for m in orgmembers:
            user = m.user; profile = user.profile
            creditsTuple = OrbitCmeOffer.objects.sumCredits(user, startDate, endDate)
            overallCreditsRedeemed, overallCreditsUnredeemed = (float(cred) for cred in creditsTuple) 
            overallCreditsEarned = overallCreditsRedeemed + overallCreditsUnredeemed
            data.append({
                'NPINumber': profile.npiNumber,
                'First Name': profile.firstName,
                'Last Name': profile.lastName,
                'Credits': overallCreditsEarned,
                'Status': m.enterpriseStatus
            })
        # sort results by credits desc, lastname asc
        data.sort(key=itemgetter('Last Name')) # stable sort
        data.sort(key=itemgetter('Credits'), reverse=True) # primary sort
        # write results to contentfile
        cf = makeCsvForAttachment(outputFields, data)
        # string formatted dates for subject line and attachment file names
        startRds = startDate.strftime('%b%d%Y')
        endRds = endDate.strftime('%b%d%Y')
        startSubjRds = startDate.strftime('%b/%d/%Y')
        endSubjRds = endDate.strftime('%b/%d/%Y')
        # set email recipients
        from_email = settings.EMAIL_FROM
        cc_emails = []
        if settings.ENV_TYPE == settings.ENV_PROD:
            to_emails = [settings.FOUNDER_EMAIL,]
            bcc_emails = [settings.DEV_EMAILS[0],]
        else:
            # internal testing
            to_emails = [settings.DEV_EMAILS[0],]
            bcc_emails = []
        subject = "Orbit Provider Credits Report for {0.name} ({1}-{2})".format(org, startSubjRds, endSubjRds)
        reportFileName = 'orbit-earnedcredits-{0}-{1}.csv'.format(startRds, endRds)
        # data for context
        ctx = {
            'organization': org,
            'startDate': startDate,
            'endDate': endDate,
        }
        message = get_template('email/org_earnedcredit_report.html').render(ctx)
        try:
            sendEmailWithAttachment(subject,
                message,
                cf,
                reportFileName,
                from_email,
                to_emails, cc_emails, bcc_emails)
        except SMTPException as e:
            logger.exception('makeOrgCreditReport send email failed')
        else:
            logger.info('makeOrgCreditReport done')
            self.stdout.write('makeOrgCreditReport done')
