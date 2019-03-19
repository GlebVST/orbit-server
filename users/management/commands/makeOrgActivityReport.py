import logging
import csv
import StringIO
from datetime import datetime, timedelta
import io
import pytz
from smtplib import SMTPException
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db.models import Subquery
from django.template.loader import get_template
from django.utils import timezone
from users.models import User, Profile, Entry, BrowserCme, Organization, OrgMember

logger = logging.getLogger('mgmt.orgacr')

# Accepted date format for command-line arguments startdate, enddate
DATE_FORMAT = '%Y-%m-%d'
DEV_EMAILS = ['faria@orbitcme.com', 'logicalmath333@gmail.com']
outputFields = (
    'Status',
    'Group',
    'LastName',
    'FirstName',
    'NPI',
    'Degree',
    'Specialty',
    'SearchDate',
    'Credit',
    'Topic',
    'Article',
    'ArticleTags',
)

IGNORE_USERS = (
    'faria@orbitcme.com',
    'gleb@codeabovelab.com',
    'glebst@codeabovelab.com',
    'mch@codeabovelab.com',
    'ram@corephysicsreview.com',
    'faria.chowdhury@gmail.com',
    'glebst@gmailcom',
    'mchwang@yahoo.com',
    'alexisarbeit@gmail.com',
    'testsand@weppa.org',
)

STRIP_CHARS = (
    u': American Journal of Roentgenology',
    u'The Radiology Assistant'
)

def cleanDescription(d):
    d2 = d
    for phrase in STRIP_CHARS:
        if phrase in d:
            d2 = d.replace(phrase, '')
            break
    return d2

class Command(BaseCommand):
    help = "Generate Article activity report for the specified Org and date range."

    def getEntries(self, org, startDate, endDate):
        """Construct BrowserCme queryset for the given Organization and date range
        Args:
            org: Organization
            startDate: utc datetime (inclusive)
            endDate: utc datetime (exclusive)
        Returns: tuple (BrowserCme queryset, profileById:dict, orgMembersByUserid:dict)
        """
        msg = "Getting entries for {0} from {1:%Y-%m-%d} until {2:%Y-%m-%d}".format(org, startDate, endDate)
        logger.info(msg)
        self.stdout.write(msg)
        # omit pending members since they have not joined yet
        orgmembers = OrgMember.objects \
                .select_related('group') \
                .filter(organization=org, pending=False)
        profiles = Profile.objects \
            .prefetch_related('degrees','specialties') \
            .filter(user__in=Subquery(orgmembers.values('user'))) \
            .order_by('user_id')
        filter_kwargs = dict(
            entry__valid=True,
            entry__activityDate__gte=startDate,
            entry__activityDate__lt=endDate,
            entry__user__in=Subquery(orgmembers.values('user'))
        )
        qset = BrowserCme.objects.select_related('entry').filter(**filter_kwargs)
        if org.joinCode == 'orbit' and settings.ENV_TYPE == settings.ENV_PROD:
            # exclude IGNORE_USERS
            omit_users = User.objects.filter(email__in=IGNORE_USERS).values_list('id', flat=True)
            qset = qset.exclude(entry__user__in=list(omit_users))
        qset = qset.order_by('entry__activityDate')
        #print(qset.query)
        profilesById = dict()
        for p in profiles:
            profilesById[p.pk] = p
        orgMembersByUserid = dict()
        for m in orgmembers:
            orgMembersByUserid[m.user.pk] = m
        return (qset, profilesById, orgMembersByUserid)

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('orgcode',
            help='Organization joincode. One word (no whitespace). Must already exist in the db.')
        parser.add_argument('startdate',
            help='Report start date in YYYY-MM-DD. This date is inclusive.'
        )
        parser.add_argument('enddate',
            help='Report end date in YYYY-MM-DD. This date is exclusive.'
        )

    def handle(self, *args, **options):
        # validate options
        try:
            org = Organization.objects.get(joinCode__iexact=options['orgcode'])
        except Organization.DoesNotExist:
            self.stderr.write('Invalid Organization joinCode: {0} (does not exist)'.format(options['orgcode']))
            return
        try:
            sd = datetime.strptime(options['startdate'], DATE_FORMAT)
            startDate = timezone.make_aware(sd)
        except ValueError:
            self.stderr.write('Invalid startdate: ValueError')
            return

        try:
            ed = datetime.strptime(options['enddate'], DATE_FORMAT)
            endDate = timezone.make_aware(ed)
        except ValueError:
            self.stderr.write('Invalid enddate: ValueError')
            return
        if startDate >= endDate:
            self.stderr.write('Invalid date range. startdate must be prior to enddate.')
            return

        # get user and activity data
        qset, profilesById, orgMembersByUserid = self.getEntries(org, startDate, endDate)
        results = []
        for m in qset:
            user = m.entry.user
            profile = profilesById[user.pk]
            orgmember = orgMembersByUserid[user.pk]
            d = dict()
            for k in outputFields:
                d[k] = ''
            d['Status'] = orgmember.getEnterpriseStatus()
            if orgmember.group:
                d['Group'] = orgmember.group.name
            d['NPI'] = profile.npiNumber
            if profile.lastName:
                d['LastName'] = profile.lastName.capitalize()
            if profile.firstName:
                d['FirstName'] = profile.firstName.capitalize()
            # --
            d['Degree'] = profile.formatDegrees()
            d['Specialty'] = profile.formatSpecialties()
            d['SearchDate'] = m.entry.activityDate.strftime('%Y-%m-%d')
            d['Credit'] = str(m.credits)
            d['Topic'] = cleanDescription(m.entry.description.encode("ascii", errors="ignore").decode())
            d['Article'] = m.url
            d['ArticleTags'] = m.entry.formatTags()
            results.append(d)
        # write results to file
        #output = io.StringIO() # TODO: use in py3
        output = io.BytesIO()
        writer = csv.DictWriter(output, delimiter=',', fieldnames=outputFields)
        writer.writeheader()
        for row in results:
            writer.writerow(row)
        cf = output.getvalue() # to be used as attachment for EmailMessage
        startReportDate = startDate
        endReportDate = endDate
        # string formatted dates for subject line and attachment file names
        startRds = startReportDate.strftime('%b%d%Y')
        endRds = endReportDate.strftime('%b%d%Y')
        startSubjRds = startReportDate.strftime('%b/%d/%Y')
        endSubjRds = endReportDate.strftime('%b/%d/%Y')
        # create EmailMessage
        from_email = settings.EMAIL_FROM
        if settings.ENV_TYPE == settings.ENV_PROD:
            to_emails = ['ram@orbitcme.com']
            cc_emails = ['ram@orbitcme.com']
            bcc_emails = DEV_EMAILS
        else:
            # internal testing
            to_emails = DEV_EMAILS
            cc_emails = []
            bcc_emails = []
        subject = "Orbit Activity Report for {0.name} ({1}-{2})".format(org, startSubjRds, endSubjRds)
        reportFileName = 'orbit-report-{0}-{1}.csv'.format(startRds, endRds)
        #
        # data for context
        #
        ctx = {
            'organization': org,
            'startDate': startDate,
            'endDate': endDate,
        }
        message = get_template('email/org_activity_report.html').render(ctx)
        msg = EmailMessage(
                subject,
                message,
                to=to_emails,
                cc=cc_emails,
                bcc=bcc_emails,
                from_email=from_email)
        msg.content_subtype = 'html'
        msg.attach(reportFileName, cf, 'application/octet-stream')
        try:
            msg.send()
        except SMTPException as e:
            logger.exception('makeOrgActivityReport send email failed')
        else:
            logger.info('makeOrgActivityReport done')
            self.stdout.write('makeOrgActivityReport done')
