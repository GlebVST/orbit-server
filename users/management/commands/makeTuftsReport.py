import logging
from datetime import datetime, timedelta
import pytz
from smtplib import SMTPException
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.template.loader import get_template
from django.utils import timezone
from users.tuftsutils import MainReport, TUFTS_RECIPIENTS

logger = logging.getLogger('mgmt.tuftqr')

DEV_EMAILS = settings.DEV_EMAILS[0:1]
MANAGER_EMAILS = [settings.MANAGERS[0][1]]

# reportType (used by email subject)
REPORT_QUARTER = 'Quarterly'
REPORT_ANNUAL = 'Annual'
# used by calcYearReportDateRange
ANNUAL_REPORT_MONTH = 6
ANNUAL_REPORT_DAY = 30

# quarterly month ranges
DATE_RANGE_MAP = {
    1: ((10, 1), (12, 31)), # Q4
    4: ((1, 1), (3, 31)), # Q1
    7: ((4, 1), (6, 30)), # Q2
    10: ((7,1), (9, 30)), # Q3
}

class Command(BaseCommand):
    help = "Generate quarterly Tufts Report for the current quarter. This should be run on 1/1, 4/1, 7/1 and 10/1."

    def calcReportDateRange(self, options):
        """Calculate quarterly report date range
        Returns tuple: (startDate: datetime, endDate: datetime)
        """
        now = timezone.now()
        if options['report_month'] and options['report_year']:
            mkey = options['report_month']
            year = options['report_year']
        else:
            mkey = now.month
            year = now.year
            if now.month == 1:
                year -= 1 # calculate for Q4 of previous year
            # clamp mkey to one of: 1/4/7/10
            if mkey not in DATE_RANGE_MAP:
                # find closest on-going quarter
                if mkey in (2, 3):
                    mkey = 4 # Q1: 1/1 - 3/31
                elif mkey in (5, 6):
                    mkey = 7 # Q2: 4/1 - 6/30
                elif mkey in (8, 9):
                    mkey = 10 # Q3: 7/1 - 9/30
                elif mkey in (11, 12):
                    mkey = 1 # Q4: 10/1 - 12/31
        # get the date range for a specific quarter
        s, e = DATE_RANGE_MAP[mkey]
        startDate = datetime(year, s[0], s[1], tzinfo=pytz.utc)
        endDate = datetime(year, e[0], e[1], 23, 59, 59, tzinfo=pytz.utc)
        return (startDate, endDate)

    def calcYearReportDateRange(self, year):
        """Calculate annual report date range
        Args:
            year: int - used for the year of endDate
        e.g. endDate = 2020-06-30 23:59:59 utc
         startDate = 2019-06-30 00:00:00 utc
        Returns tuple: (startDate: datetime, endDate: datetime)
        """
        endDate = datetime(year, ANNUAL_REPORT_MONTH, ANNUAL_REPORT_DAY, 23, 59, 59, tzinfo=pytz.utc)
        startDate = datetime(year-1, ANNUAL_REPORT_MONTH, ANNUAL_REPORT_DAY, tzinfo=pytz.utc)
        return (startDate, endDate)

    def add_arguments(self, parser):
        parser.add_argument(
            '--report_month',
            type=int,
            const=0,
            nargs='?',
            help='Specify start month of 1, 4, 7, or 10. Default behavior uses now timestamp to calculate report dates'
        )
        parser.add_argument(
            '--report_year',
            type=int,
            const=0,
            nargs='?',
            help='Specify start year. Default behavior uses now timestamp to calculate report dates'
        )
        parser.add_argument(
            '--managers_only',
            action='store_true',
            dest='managers_only',
            default=False,
            help='Only email reports to MANAGERS. Default behavior is to include Tufts recipients in prod env. Test env never includes Tufts recipients.'
        )
        parser.add_argument(
            '--end_of_year',
            action='store_true',
            dest='end_of_year',
            default=False,
            help='If True: all entries from the previous year are included in the report. This option is set by the cron task that should execute on July 1 UTC each year.'
        )


    def createReport(self, startDate, endDate, options):
        """Calculate data and create EmailMessage
        """
        reportType = REPORT_QUARTER
        if self.isEndOfYearReport:
            reportType = REPORT_ANNUAL
        mainReport = MainReport(startDate, endDate,
            settings.GAUTH_SERVICE_CREDENTIALS_FILE,
            settings.GSHEET_TUFTS_EVAL_DOCID,
        )
        mainReport.getEntries()
        results = mainReport.makeReportData()
        # write results to StringIO csv file
        cf = mainReport.createReportCsv(results)
        
        startReportDate = startDate
        # endDate is y-m-d 23:59:59 so display shows d+1
        endReportDate = endDate + timedelta(days=1)
        
        # make summaryCsv
        ctx = mainReport.makeContext()
        summaryCsvFile = mainReport.createSummaryCsv(ctx, startReportDate, endReportDate)
        summary = summaryCsvFile.getvalue()
        
        # create EmailMessage
        from_email = settings.EMAIL_FROM
        to_emails = DEV_EMAILS
        cc_emails = []; bcc_emails = []
        if settings.ENV_TYPE == settings.ENV_PROD:
            to_emails = MANAGER_EMAILS[:] # make copy before calling extend
            if not options['managers_only']:
                to_emails.extend(TUFTS_RECIPIENTS)
            cc_emails = []; bcc_emails = DEV_EMAILS
        else:
            # NOTE: below line is for testing
            to_emails = DEV_EMAILS
            cc_emails = []; bcc_emails = []
        subject = "Orbit {0} Report ({1}-{2})".format(
            reportType,
            startReportDate.strftime('%b/%d/%Y'),
            endReportDate.strftime('%b/%d/%Y')
        )
        if self.isEndOfYearReport:
            startRds = startReportDate.strftime('%b%d%Y')
            endRds = endReportDate.strftime('%b%d%Y')
            reportFileName = 'orbit-annual-report-{0}-{1}.csv'.format(startRds, endRds)
            summaryFileName = 'orbit-annual-summary-{0}-{1}.csv'.format(startRds, endRds)
        else:
            startRds = startReportDate.strftime('%b%Y')
            endRds = endReportDate.strftime('%b%Y')
            reportFileName = 'orbit-report-{0}-{1}.csv'.format(startRds, endRds)
            summaryFileName = 'orbit-summary-{0}-{1}.csv'.format(startRds, endRds)
        
        message = get_template('email/tufts_quarterly_report.html').render(ctx)
        msg = EmailMessage(
                subject,
                message,
                to=to_emails,
                cc=cc_emails,
                bcc=bcc_emails,
                from_email=from_email)
        msg.content_subtype = 'html'
        msg.attach(reportFileName, cf, 'application/octet-stream')
        msg.attach(summaryFileName, summary, 'application/octet-stream')
        return msg

    def handle(self, *args, **options):
        try:
            # options error check
            if options['end_of_year']:
                self.isEndOfYearReport = True
                if not options['report_year']:
                    now = timezone.now()
                    year = now.year
                else:
                    year = options['report_year']
                startDate, endDate = self.calcYearReportDateRange(year)
            else:
                self.isEndOfYearReport = False
                if (options['report_month'] and not options['report_year']) or (options['report_year'] and not options['report_month']):
                    self.stderr.write('If specified, both report_month and report_year must be specified together')
                    return
                if options['report_month'] and options['report_month'] not in DATE_RANGE_MAP:
                    self.stderr.write('Report month must be one of: 1, 4, 7, or 10')
                    return
                startDate, endDate = self.calcReportDateRange(options)
            msg = self.createReport(startDate, endDate, options)
            msg.send()
        except SMTPException as e:
            logger.exception('makeTuftsReport send email failed')
        except Exception as e:
            logger.exception('makeTuftsReport fatal exception')
        else:
            logger.info('makeTuftsReport send email done')
