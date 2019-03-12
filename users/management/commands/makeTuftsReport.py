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
from users.models import User, Profile, Entry, BrowserCme, UserFeedback
from pprint import pprint

logger = logging.getLogger('mgmt.tuftsqr')

TUFTS_RECIPIENTS = [
    'Mirosleidy.Tejeda@tufts.edu',
    'Karin.Pearson@tufts.edu',
    'Jennifer.Besaw@tufts.edu'
]

outputFields = (
    'LastName',
    'FirstName',
    'Degree',
    'NPI #',
    'Search Date',
    'Credit Earned',
    'Attendee Type (Physician or Other)',
    'TopicSearched',
    'Article/Website Consulted',
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

# quarterly month ranges
DATE_RANGE_MAP = {
    1: ((10, 1), (12, 31)), # Q4
    4: ((1, 1), (3, 31)), # Q1
    7: ((4, 1), (6, 30)), # Q2
    10: ((7,1), (9, 30)), # Q3
}

OTHER = 'Other (combined)'
RESPONSE_MAP = {
        BrowserCme.RESPONSE_YES: 'Yes',
        BrowserCme.RESPONSE_NO: 'No',
        BrowserCme.RESPONSE_UNSURE: 'Unsure'
}

RESPONSE_CHOICES = (
    BrowserCme.RESPONSE_YES,
    BrowserCme.RESPONSE_NO,
    BrowserCme.RESPONSE_UNSURE
)

PLAN_EFFECT_CHOICES = (
    BrowserCme.RESPONSE_YES,
    BrowserCme.RESPONSE_NO,
)
PLAN_TEXT_CHOICES = (
    BrowserCme.DIFFERENTIAL_DIAGNOSIS,
    BrowserCme.TREATMENT_PLAN,
    BrowserCme.DIAGNOSTIC_TEST
)
J = u': American Journal of Roentgenology'

def cleanDescription(d):
    d2 = d
    if J in d:
        idx = d.index(J)
        d2 = d[0:idx]
    return d2


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

    def getEntries(self, startDate, endDate):
        """Returns BrowserCme queryset for a specific date range
        Args:
            startDate: utc datetime
            endDate: utc datetime
        """
        msg = "Getting entries from {0:%Y-%m-%d} to {1:%Y-%m-%d}".format(startDate, endDate)
        logger.info(msg)
        self.stdout.write(msg)
        filter_kwargs = dict(
            entry__valid=True,
            entry__activityDate__gte=startDate,
            entry__activityDate__lte=endDate
        )
        omit_users = User.objects.filter(email__in=IGNORE_USERS).values_list('id', flat=True)
        omit_userids = list(omit_users)
        qset = BrowserCme.objects.select_related('entry').filter(**filter_kwargs).exclude(
                entry__user__in=omit_userids).order_by('entry__activityDate')
        #print(qset.query)
        ekwargs = dict(
            valid=True,
            activityDate__gte=startDate,
            activityDate__lte=endDate
        )
        # get distinct profiles in this date range
        qsu = Entry.objects.filter(**ekwargs).exclude(user__in=omit_userids)
        profiles = Profile.objects.filter(user__in=Subquery(qsu.values('user'))).order_by('user_id')
        return (qset, profiles, startDate, endDate)

    def calcResponseStats(self, qset, fieldname):
        """Calculate YES/NO/UNSURE stats for the given field
        Args:
            qset: queryset from getEntries
            fieldname: one of: competence/performance/commercialBias
        Returns: a tuple of (1) list of dicts w. keys: value, count, pct
                 and (2) list of comments for that particular field
                 (if any)
        """
        num_entries = qset.count()
        stats = []
        comments = []
        clause = '{0}__exact'.format(fieldname)
        for v in RESPONSE_CHOICES:
            filter_kwargs = {clause: v}
            cnt = qset.filter(**filter_kwargs).count()
            pct = 100.0*cnt/num_entries
            nv = RESPONSE_MAP[v]
            stats.append(dict(value=nv, count=cnt, pct=pct))
        if (fieldname == "commercialBias"):
            for m in qset:
                cb = m.commercialBiasText
                if (cb != ''):
                    comments.append(cb)

        return (stats, comments)

    def calcPlanStats(self, qset):
        """Calculate stats on planEffect and planText
        Returns: tuple (
            planEffectStats: list of dicts w. keys value, count, pct
            planTextStats: list of dicts w. keys value, count, pct
            planTextOther: list of strs
        """
        num_entries = qset.count()
        planEffectStats = []
        for v in PLAN_EFFECT_CHOICES:
            filter_kwargs = {'planEffect': v}
            cnt = qset.filter(**filter_kwargs).count()
            pct = 100.0*cnt/num_entries
            nv = RESPONSE_MAP[v]
            planEffectStats.append(dict(value=nv, count=cnt, pct=pct))
        # planText: partition into keyed responses vs Other
        planTextDict = {
            BrowserCme.DIFFERENTIAL_DIAGNOSIS: 0,
            BrowserCme.TREATMENT_PLAN: 0,
            BrowserCme.DIAGNOSTIC_TEST: 0
        }
        planTextOther = []
        for m in qset:
            pt = m.planText
            if pt in planTextDict:
                # keyed response
                planTextDict[pt] += 1
            else:
                planTextOther.append(pt)
        # calculate pct
        planTextStats = []
        for v in PLAN_TEXT_CHOICES:
            cnt = planTextDict[v]
            pct = 100.0*cnt/num_entries
            planTextStats.append(dict(value=v, count=cnt, pct=pct))
        #pprint(planTextStats)
        return (planEffectStats, planTextStats, planTextOther)

    def calcTagStats(self, qset):
        """
        Args:
            qset: BrowserCme queryset
        Returns: list of dicts w. keys: tagname, pct, count
        """
        counts = {
            OTHER: {'count': 0, 'pct': 0}
        }
        for m in qset:
            tags = m.entry.tags.all()
            tag_names = [t.name for t in tags]
            for tagname in tag_names:
                if tagname in counts:
                    counts[tagname]['count'] += 1
                else:
                    counts[tagname] = {'count': 1, 'pct': 0}
        total = 0
        for tagname in counts:
            total += counts[tagname]['count'] # OTHER is still at 0
        # calculate percentages and combine small pcts into OTHER
        for tagname in sorted(counts):
            if tagname == OTHER:
                continue
            tagcount = counts[tagname]['count']
            tagpct = 100.0*tagcount/total
            counts[tagname]['pct'] = tagpct
            #print("{0} {1} {2}".format(tagname, tagcount, tagpct))
            if tagpct < 1:
                counts[OTHER]['count'] += tagcount
                counts[OTHER]['pct'] += tagpct
        tag_stats = []
        for tagname in sorted(counts):
            tagpct = counts[tagname]['pct']
            if tagpct < 1:
                continue
            tag_stats.append(dict(
                tagname=tagname,
                pct=tagpct,
                count=counts[tagname]['count']
            ))
        return tag_stats

    def getEntryDescriptions(self, qset):
        """Get and clean entry__description from the given queryset
        Args:
            qset: BrowserCme queryset
        Returns: list of strs
        """
        descriptions = []
        vqset = qset.values_list('entry__description', flat=True).distinct().order_by('entry__description')
        for v in vqset:
            descr = v.strip()
            if descr.startswith('www.') and (descr.endswith('.org') or descr.endswith('.gov') or descr.endswith('.com')):
                continue
            descr = cleanDescription(descr)
            if not descr:
                continue
            descriptions.append(descr)
        return descriptions

    def getVal(self, ctx, key, subvalue, subkey = 'value'):
        """Create a string for displaying counts in the csv file. This
        is the number of BrowserCme entries. The dict in ctx that has
        'pct' key also has a 'count' key which is being used here.
        Args:
            ctx: dictionary containing the stats
            key: key in ctx whose value will be another dictionary
            subvalue: value in ctx[key] dictionary
            subkey: key in ctx[key] dictionary
        """
        numEntries = '0'
        for k in ctx[key]:
            if (k[subkey] == subvalue):
                numEntries = '%d' % int(k['count'])
        return numEntries

    def getTagEntry(self, ctx, tagList, tagIdx): 
        """ Gets the tagEntry corresponding to the tagIdx in tagList
            Also returns an updated tagIdx
        Args:
            ctx: dictionary containing the stats
            tagList: list of specialty tags
            tagIdx: index into list 
        """
        tagEntry = ''
        if (tagIdx < len(tagList)):
            tagCnt = self.getVal(ctx, 'tags', tagList[tagIdx], 'tagname')
            tagEntry = tagList[tagIdx] + ' - ' + tagCnt
            tagIdx += 1
        return (tagEntry, tagIdx)

    def createSummaryCsv(self, ctx, qset):
        """Create a summary of the stats in csv format. To be used as an attachment
        Args:
            ctx: dictionary containing the stats
            qset: BrowserCme queryset for a specific date range based on now timestamp
        Returns: stats in csv format
        """
        csvfile = StringIO.StringIO()
        wr = csv.writer(csvfile)

        startReportDate = ctx['startDate']
        endReportDate = ctx['endDate'] + timedelta(days=1) # use reportDate instead of now since cmd can be run at any time
        # string formatted dates
        startSubjRds = startReportDate.strftime('%b/%d/%Y')
        endSubjRds = endReportDate.strftime('%b/%d/%Y')

        # Column A
        columnA = ['Report Timeframe: ' + startSubjRds + ' - ' + endSubjRds, 'Overall Evaluation Participants N = ']

        # Column B
        competenceNum = self.getVal(ctx, 'competence', 'Yes')
        performanceNum = self.getVal(ctx, 'performance', 'Yes')
        competenceUnsureNum = self.getVal(ctx, 'competence', 'Unsure')
        performanceUnsureNum = self.getVal(ctx, 'performance', 'Unsure')
        unsureNum = int(competenceUnsureNum) + int(performanceUnsureNum)
        columnB = ['', str(ctx['numUsers']), 'Conducting this search will result in a change in my:', 
                   'Competence - ' + competenceNum, 'Performance - ' + performanceNum,
                   'Unsure - ' + '%d' % unsureNum]

        # Column C
        planEffectNum = self.getVal(ctx, 'planEffect', 'Yes')
        planEffectNoNum = self.getVal(ctx, 'planEffect', 'No')
        columnC = ['', '', 'Did this information change your clinical plan?',
                   'Yes - ' + planEffectNum, 'No - ' + planEffectNoNum]

        # Column D
        planChangeDiffDiag = self.getVal(ctx, 'planText',
                                            unicode('Differential diagnosis'))
        planChangeDiagTest = self.getVal(ctx, 'planText',
                                            unicode('Diagnostic tests'))
        planChangeTreatPlan = self.getVal(ctx, 'planText',
                                             unicode('Treatment plan'))
        # Determine if we will need add any text to the 'Other (Please explain)'
        # cell and add it if we have any text in planTextOther
        planTextOther = ctx['planTextOther']
        nonEmptyPlanTextOther = []
        for text in planTextOther:
            if text != u'':
                nonEmptyPlanTextOther.append(text)
        otherPleaseExplainAdd = '' if (len(nonEmptyPlanTextOther) == 0) else nonEmptyPlanTextOther[0]
        columnD = ['', '', 'If yes, how?', 'Differential diagnosis - ' + planChangeDiffDiag,
                   'Diagnostic tests - ' + planChangeDiagTest, 'Treatment plan - ' + planChangeTreatPlan,
                   'Other (Please explain)' + otherPleaseExplainAdd]
        # Add the other text, if any, in the column in the rows that follow
        planTextOtherIdx = 1
        while (planTextOtherIdx < len(nonEmptyPlanTextOther)):
            columnD.append(nonEmptyPlanTextOther[planTextOtherIdx])
            planTextOtherIdx += 1

        # Column E
        columnE = ['', '', 'Select relevant specialty tags to categorize this credit']
        # this is for the specialty tags column, it needs to be alphabetized
        # (except for the Other (combined) tag which I put at the end)
        tagnames = [''] * len(ctx['tags'])
        addOther = 0
        i = 0
        for tag in ctx['tags']:
            if (tag['pct'] > 0):
                if (tag['tagname'] != 'Other (combined)'):
                    tagnames[i] = tag['tagname']
                    i += 1
                else:
                    addOther = 1

        tagnames.sort()

        if (addOther):
            tagnames.append('Other (combined)')

        # calibrate tagnameIdx to point to the first non-empty tagname
        # we have empty tag-names b/c some tagnames may be associated
        # with a 0 percent, in which case we should not list them
        # and they are marked with a blank string
        tagnameIdx = 0
        while (tagnames[tagnameIdx] == ''):
            tagnameIdx += 1

        while (tagnameIdx < len(tagnames)):
            (tagEntry, tagnameIdx) = self.getTagEntry(ctx, tagnames,
                                                      tagnameIdx)
            columnE.append(tagEntry)

        # Column F
        commBiasYesNum = self.getVal(ctx, 'commBias', 'Yes')
        commBiasNoNum = self.getVal(ctx, 'commBias', 'No')
        commBiasUnsureNum = self.getVal(ctx, 'commBias', 'Unsure')

        columnF = ['', '', 'Did you perceive commercial bias in the content?',
                   'Yes - ' + commBiasYesNum, 'No - ' + commBiasNoNum, 
                   'Unsure - ' + commBiasUnsureNum]
        
        # Column G
        columnG = ['', '', 'If yes, explain']

        # Grab the comments list of commercial bias
        commBiasComments = self.calcResponseStats(qset, 'commercialBias')[1]
        columnG += commBiasComments

        # Column H
        columnH = ['', '', 'Please provide any feedback/comments regarding the articles, or the overall system effectiveness']

        # entrySpecific entries have an article url inside of them
        entrySpecific = UserFeedback.objects.filter(entry__isnull=False, created__gte=startReportDate, created__lte=endReportDate).order_by('created')

        columnH += entrySpecific

        # Determine max length so we can create a matrix that can be transposed
        maxLength = max(len(columnA), len(columnB), len(columnC), len(columnD), 
                        len(columnE), len(columnF), len(columnG), len(columnH))


        columnA += [''] * (maxLength - len(columnA) + 1)
        columnB += [''] * (maxLength - len(columnB) + 1)
        columnC += [''] * (maxLength - len(columnC) + 1)
        columnD += [''] * (maxLength - len(columnD) + 1)
        columnE += [''] * (maxLength - len(columnE) + 1)
        columnF += [''] * (maxLength - len(columnF) + 1)
        columnG += [''] * (maxLength - len(columnG) + 1)
        columnH += [''] * (maxLength - len(columnH) + 1)

        columnA[maxLength] = "Total # of respondents - " + str(ctx['numUsers'])  

        columnBased = [columnA, columnB, columnC, columnD, columnE, columnF, columnG, columnH]
        # Transpose this array of columns to an array of rows that can be easily
        # written as a csv
        rowBased = zip(*columnBased)

        for row in rowBased:
            wr.writerow(row)

        return csvfile

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

    def handle(self, *args, **options):
        # options error check
        if (options['report_month'] and not options['report_year']) or (options['report_year'] and not options['report_month']):
            self.stderr.write('If specified, both report_month and report_year must be specified together')
            return
        if options['report_month'] and options['report_month'] not in DATE_RANGE_MAP:
            self.stderr.write('Report month must be one of: 1, 4, 7, or 10')
            return
        startDate, endDate = self.calcReportDateRange(options)
        # get brcme entries
        qset, profiles, startDate, endDate = self.getEntries(startDate, endDate)
        # profiles for the distinct users in qset
        profilesById = dict()
        for p in profiles:
            profilesById[p.pk] = p
        results = []
        for m in qset:
            user = m.entry.user
            profile = profilesById[user.pk]
            d = dict()
            for k in outputFields:
                d[k] = ''
            d['NPI #'] = profile.npiNumber
            if profile.isPhysician():
                d['Attendee Type (Physician or Other)'] = 'Physician'
            else:
                d['Attendee Type (Physician or Other)'] = 'Other'
            if profile.lastName:
                d['LastName'] = profile.lastName.capitalize()
            elif profile.npiLastName:
                d['LastName'] = profile.npiLastName
            if profile.firstName:
                d['FirstName'] = profile.firstName.capitalize()
            elif profile.npiFirstName:
                d['FirstName'] = profile.npiFirstName
            if d['LastName'] == '' or d['FirstName'] == '':
                logger.warning('Incomplete profile for {0.email}'.format(user))
                continue
            # --
            d['Degree'] = profile.formatDegrees()
            d['Search Date'] = m.entry.activityDate.strftime('%Y-%m-%d')
            d['Credit Earned'] = str(m.credits)
            d['TopicSearched'] = m.entry.description.encode("ascii", errors="ignore").decode()
            d['Article/Website Consulted'] = m.url
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
        endReportDate = endDate + timedelta(days=1) # use reportDate instead of now since cmd can be run at any time
        # string formatted dates for subject line and attachment file names
        startRds = startReportDate.strftime('%b%Y')
        endRds = endReportDate.strftime('%b%Y')
        startSubjRds = startReportDate.strftime('%b/%d/%Y')
        endSubjRds = endReportDate.strftime('%b/%d/%Y')
        # create EmailMessage
        from_email = settings.EMAIL_FROM
        cc_emails = ['ram@orbitcme.com']
        bcc_emails = ['faria@orbitcme.com', 'logicalmath333@gmail.com']
        if settings.ENV_TYPE == settings.ENV_PROD:
            to_emails = ['ram@orbitcme.com']
            if not options['managers_only']:
                to_emails.extend(TUFTS_RECIPIENTS)
        else:
            # NOTE: below line is for testing
            to_emails = ['ram@orbitcme.com']
        subject = "Orbit Quarterly Report ({0}-{1})".format(startSubjRds, endSubjRds)
        reportFileName = 'orbit-report-{0}-{1}.csv'.format(startRds, endRds)
        #
        # data for context
        #
        planEffectStats, planTextStats, planTextOther = self.calcPlanStats(qset)
        ctx = {
            'startDate': startDate,
            'endDate': endDate,
            'numUsers': len(profiles),
            'tags': self.calcTagStats(qset),
            'competence': self.calcResponseStats(qset, 'competence')[0],
            'performance': self.calcResponseStats(qset, 'performance')[0],
            'commBias': self.calcResponseStats(qset, 'commercialBias')[0],
            'descriptions': self.getEntryDescriptions(qset),
            'planEffect': planEffectStats,
            'planText': planTextStats,
            'planTextOther': planTextOther,
        }
        message = get_template('email/tufts_quarterly_report.html').render(ctx)
        msg = EmailMessage(
                subject,
                message,
                to=to_emails,
                cc=cc_emails,
                bcc=bcc_emails,
                from_email=from_email)
        msg.content_subtype = 'html'

        # summary of stats csv attachment
        summaryCsvFile = self.createSummaryCsv(ctx, qset)
        summary = summaryCsvFile.getvalue()
        summaryFileName = 'orbit-summary-{0}-{1}.csv'.format(startRds, endRds)

        msg.attach(reportFileName, cf, 'application/octet-stream')
        msg.attach(summaryFileName, summary, 'application/octet-stream')
        try:
            msg.send()
        except SMTPException as e:
            logger.exception('makeTuftsReport send email failed')
        else:
            logger.info('makeTuftsReport send email done')
