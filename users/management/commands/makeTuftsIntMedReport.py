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

logger = logging.getLogger('mgmt.tuftim')

class Command(BaseCommand):
    help = "Generate Tufts Report for Internal Medicine providers with completed profile."

    def calcReportDateRange(self, curDate=None):
        """Calculate bimonthly report date range
        Returns tuple: (startDate: datetime, endDate: datetime)
        """
        startDate = None
        endDate = None
        if not curDate:
            curDate = timezone.now()
        today = curDate.day
        if (today == 1) or (today == 16):
            ydt = curDate - timedelta(days=1)
            endDate = datetime(ydt.year, ydt.month, ydt.day, 23, 59, 59, tzinfo=pytz.utc)
            if (today == 16):
                sday = 1
            else:
                sday = 16
            startDate = datetime(ydt.year, ydt.month, sday, tzinfo=pytz.utc)
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


    def createReport(self, startDate, endDate, options):
        """Calculate data and create EmailMessage.
        If no results for this period, we still send an email notification.
        """
        mainReport = IntMedReport(startDate, endDate,
            settings.GAUTH_SERVICE_CREDENTIALS_FILE,
            settings.GSHEET_TUFTS_EVAL_DOCID,
        )
        self.mainReport = mainReport
        mainReport.getEntries()
        if mainReport.entries.exists():
            results = mainReport.makeReportData()
            # write results to StringIO csv file
            cf = mainReport.createReportCsv(results)
            startReportDate = startDate
            endReportDate = endDate
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
        cc_emails = ['ram@orbitcme.com']
        bcc_emails = ['faria@orbitcme.com', 'logicalmath333@gmail.com']
        if settings.ENV_TYPE == settings.ENV_PROD:
            if options['dry_run']:
                to_emails = ['faria@orbitcme.com']
                cc_emails = []; bcc_emails = []
            else:
                to_emails = ['ram@orbitcme.com']
                if not options['managers_only']:
                    to_emails.extend(TUFTS_RECIPIENTS)
        else:
            # NOTE: below line is for testing
            to_emails = ['faria@orbitcme.com']
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
        #curdate = datetime(2020,5,16,tzinfo=pytz.utc)
        curdata = None
        startDate, endDate = self.calcReportDateRange(curdate)
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
            else:
                # bulk-update submitABIMDate on the reported entries
                self.mainReport.updateSubmitDate(endDate)
