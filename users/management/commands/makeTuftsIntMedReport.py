import logging
from datetime import datetime, timedelta
import pytz
from smtplib import SMTPException
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.template.loader import get_template
from django.utils import timezone
from users.tuftsutils import IntMedReport, TUFTS_RECIPIENTS

logger = logging.getLogger('mgmt.abim')

DEV_EMAILS = settings.DEV_EMAILS[0:1]
MANAGER_EMAILS = [settings.MANAGERS[0][1]]

class Command(BaseCommand):
    help = "Generate Tufts Report for Internal Medicine providers with completed profile. The command should be called daily by a cron task. The bi-monthly report will execute on days 1 and 16 of each month."

    def calcBiMonthReportDateRange(self, fixDate=None):
        """Calculate bimonthly report date range
        Args:
            fixDate: None/datetime from which to set endDate
              e.g. if fixDate = 2020-05-16 => endDate = 2020-05-15 23:59:59
            else endDate = now-1day 23:59:59 when now.day is the
              1st and 16th of the month
        Returns tuple: (startDate: datetime, endDate: datetime)
        """
        startDate = None
        endDate = None
        if not fixDate:
            fixDate = timezone.now()
        today = fixDate.day
        if (today == 1) or (today == 16):
            ydt = fixDate - timedelta(days=1)
            endDate = datetime(ydt.year, ydt.month, ydt.day, 23, 59, 59, tzinfo=pytz.utc)
            if (today == 16):
                sday = 1
            else:
                sday = 16
            startDate = datetime(ydt.year, ydt.month, sday, tzinfo=pytz.utc)
        return (startDate, endDate)

    def calcYearReportDateRange(self):
        """Calculate yearly report date range
        Returns tuple: (startDate: datetime, endDate: datetime)
        """
        startDate = None
        endDate = None
        fixDate = timezone.now()
        year = fixDate.year - 1
        endDate = datetime(year, 12, 31, 23, 59, 59, tzinfo=pytz.utc)
        startDate = datetime(year, 1, 1, tzinfo=pytz.utc)
        return (startDate, endDate)

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry_run',
            action='store_true',
            dest='dry_run',
            default=False,
            help='Dry run. Do not update submitDate on brcme entries.'
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
            help='If True: all entries from the previous year are included in the report. This option is set by the cron task that should execute on Jan 1 each year.'
        )
        parser.add_argument(
            '--bimonthly_enddate',
            type=str,
            dest='bimonthly_enddate',
            nargs='?',
            help='YYYYMMDD format. EndDate will be set to arg-1day 23:59:59. If not given, endDate is auto-set from current timestamp.'
        )


    def createReport(self, startDate, endDate, options):
        """Calculate data and create EmailMessage.
        If no results for this period, we still send an email notification.
        """
        startReportDate = startDate
        endReportDate = endDate
        mainReport = IntMedReport(startDate, endDate,
            settings.GAUTH_SERVICE_CREDENTIALS_FILE,
            settings.GSHEET_TUFTS_EVAL_DOCID,
        )
        self.mainReport = mainReport
        mainReport.getEntries(isEndOfYearReport=self.isEndOfYearReport)
        if mainReport.entries.exists():
            results = mainReport.makeReportData()
            # write results to StringIO csv file
            cf = mainReport.createReportCsv(results)
            # make summaryCsv
            ctx = mainReport.makeContext()
            summaryCsvFile = mainReport.createSummaryCsv(ctx, startReportDate, endReportDate)
            summary = summaryCsvFile.getvalue()
        else:
            cf = None # No file attachments on email 
            ctx = {
                'startDate': startDate,
                'endDate': endDate,
                'numEntries': 0
            }
        self.stdout.write('Num entries for date range {0} to {1}: {2}'.format(startDate, endDate, ctx['numEntries']))
        # create EmailMessage
        from_email = settings.EMAIL_FROM
        if settings.ENV_TYPE == settings.ENV_PROD:
            if options['dry_run']:
                to_emails = DEV_EMAILS
                cc_emails = []; bcc_emails = []
            else:
                to_emails = MANAGER_EMAILS[:] # make copy before calling extend
                if not options['managers_only']:
                    to_emails.extend(TUFTS_RECIPIENTS)
                cc_emails = []; bcc_emails = DEV_EMAILS
        else:
            # NOTE: below line is for testing
            to_emails = DEV_EMAILS
            cc_emails = []; bcc_emails = []
        subject = "Orbit Internal Medicine Report ({0}-{1})".format(
            startReportDate.strftime('%b/%d/%Y'),
            endReportDate.strftime('%b/%d/%Y')
        )
        startRds = startReportDate.strftime('%b%Y')
        endRds = endReportDate.strftime('%b%Y')
        reportFileName = 'orbit-intmedreport-{0}-{1}.csv'.format(startRds, endRds)
        summaryFileName = 'orbit-intmedsummary-{0}-{1}.csv'.format(startRds, endRds)
        
        message = get_template('email/tufts_intmed_report.html').render(ctx)
        msg = EmailMessage(
                subject,
                message,
                to=to_emails,
                cc=cc_emails,
                bcc=bcc_emails,
                from_email=from_email)
        msg.content_subtype = 'html'
        if cf:
            msg.attach(reportFileName, cf, 'application/octet-stream')
            msg.attach(summaryFileName, summary, 'application/octet-stream')
        return msg

    def handle(self, *args, **options):
        endDate = None
        if options['end_of_year']:
            # Report contains all entries whose submitABIMDate is set (i.e. all entries submitted
            # in bi-monthly reports) from Jan 1 to Dec 31 23:59:59.
            self.isEndOfYearReport = True
            startDate, endDate = self.calcYearReportDateRange()
        else:
            self.isEndOfYearReport = False
            curDate = None
            if options['bimonthly_enddate']:
                # parse date
                try:
                    curDate = datetime.strptime(options['bimonthly_enddate'], '%Y%m%d').replace(tzinfo=pytz.utc)
                except ValueError:
                    self.stdout.write("ERROR. Invalid date value: {bimonthly_enddate}. Format is YYYYMMDD.".format(**options))
                    return
            startDate, endDate = self.calcBiMonthReportDateRange(curDate)
        if not endDate:
            self.stdout.write('Exit without running')
            return
        self.stdout.write('Generating report for {0} - {1}'.format(startDate, endDate))
        try:
            msg = self.createReport(startDate, endDate, options)
            msg.send()
        except SMTPException as e:
            logger.exception('makeTuftsIntMedReport send email failed')
        except Exception as e:
            logger.exception('makeTuftsIntMedReport fatal exception')
        else:
            logger.info('makeTuftsIntMedReport send email done')
            if options['dry_run']:
                logger.info('makeTuftsIntMedReport dry_run over')
            elif not self.isEndOfYearReport:
                # bulk-update submitABIMDate on the reported entries
                self.mainReport.updateSubmitDate(endDate)
