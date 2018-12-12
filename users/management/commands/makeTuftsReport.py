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

# by month
DATE_RANGE_MAP = {
    1: ((10, 1), (12, 31)),
    4: ((1, 1), (3, 31)),
    7: ((4, 1), (6, 30)),
    10: ((7,1), (9, 30)),
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

    def getEntries(self, now):
        """Returns BrowserCme queryset for a specific date range based on now timestamp
        Args:
            now: datetime
        """
        month = now.month
        if month not in DATE_RANGE_MAP:
            if month in (2, 3):
                month = 4
            elif month in (5, 6):
                month = 7
            elif month in (8, 9):
                month = 10
            elif month in (11, 12):
                month = 1
        s, e = DATE_RANGE_MAP[month]
        year = now.year
        if now.month == 1:
            year -= 1 # calculate for previous year
        startDate = datetime(year, s[0], s[1], tzinfo=pytz.utc)
        endDate = datetime(year, e[0], e[1], 23, 59, 59, tzinfo=pytz.utc)
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
        print "clause: ", clause
        for v in RESPONSE_CHOICES:
            filter_kwargs = {clause: v}
            cnt = qset.filter(**filter_kwargs).count()
            pct = 100.0*cnt/num_entries
            nv = RESPONSE_MAP[v]
            print "v: ", v, " nv: ", nv
            stats.append(dict(value=nv, count=cnt, pct=pct))
        if (fieldname == "commercialBias"):
            for m in qset:
                cb = m.commercialBiasText
                print "commercialBias: ", cb
                if (cb != ''):
                    comments.append(cb)

        print "comments: ", comments
        return (stats, comments)

    def calcPlanStats(self, qset):
        """Calculate stats on planEffect and planText
        Returns: tuple (
            planEffectStats: list of dicts w. keys value, cnt, pct
            planTextStats: list of dicts w. keys value, cnt, pct
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
            print "m: ", m
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
        Returns: list of dicts w. keys: tagname, tagpct
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

    def getPctVal(self, ctx, key, subvalue, subkey = 'value'):
        keyPct = '0.00' #key + ' value not found'
        for k in ctx[key]:
            print k
            if (k[subkey] == subvalue):
                keyPct = '%.2f' % k['pct'] + '%'
        return keyPct

    def getTagEntry(self, ctx, tagList, tagIdx): 
        tagEntry = ''
        if (tagIdx < len(tagList)):
            tagPct = self.getPctVal(ctx, 'tags', tagList[tagIdx], 'tagname')
            tagEntry = tagList[tagIdx] + ' - ' + tagPct
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

        wr.writerow(['Report Timeframe: ' + startSubjRds + ' - ' + endSubjRds])
        wr.writerow(['Overall Evaluation Participants N = ', str(ctx['numUsers'])])

        wr.writerow(['', 'Conducting this search will result in a change ' + \
                     'in my:', 'Did this information change your clinical ' + \
                     'plan?', 'If yes, how?', 'Select relevant specialty ' + \
                     'tags to categorize this credit', 'Did you perceive ' + \
                     'commercial bias in the content?', 'If yes, explain', \
                     'Please provide any feedback/comments regarding the ' + \
                     'articles, or the overall system effectiveness'])

        # Grab the comments list of commercial bias
        commBiasComments = self.calcResponseStats(qset, 'commercialBias')[1]

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

        # this is for planTextOther, which is in the plan change column (
        # differential diagnosis, diagnostic test, treatment plan)
        

        # Determine the max number of rows
        numPlanTextRows = 4 if (len(ctx['planText']) <= 4) else len(ctx['planText'])
        numSpecialtyTags = len(tagnames) - tagnameIdx
        numCommBiasComments = len(commBiasComments)

        print "numPlanTextRows, ", numPlanTextRows
        print "numSpecialtyTags, ", numSpecialtyTags
        print "numCommBiasComments, ", numCommBiasComments
        print "planTextOther, ", ctx['planTextOther']

        maxNumRows = max([numPlanTextRows, numSpecialtyTags, numCommBiasComments])

        print "ctx['planText']: ", ctx['planText']
        print "len of ctx['planText']: ", len(ctx['planText'])

        rowIdx = 0

        # Fourth row is ''/Competence - #/Yes - #/Differential Diagnosis - #/
        # First Tag - #/Yes - #/List all comments/List all comments
        competencePct = self.getPctVal(ctx, 'competence', 'Yes')
        planEffectPct = self.getPctVal(ctx, 'planEffect', 'Yes')
        planChangeDiffDiag = self.getPctVal(ctx, 'planText', 
                                            unicode('Differential diagnosis'))
        (firstTagEntry, tagnameIdx) = self.getTagEntry(ctx, tagnames, 
                                                       tagnameIdx)
        commBiasYesPct = self.getPctVal(ctx, 'commBias', 'Yes')
        firstCommBiasComment = '' if (rowIdx > len(commBiasComments) - 1) \
                                  else commBiasComments[rowIdx]

        wr.writerow(['', 'Competence - ' + competencePct, 
                     'Yes - ' + planEffectPct, 
                     'Differential diagnosis - ' + planChangeDiffDiag,
                     firstTagEntry, 'Yes - ' + commBiasYesPct,
                     firstCommBiasComment])

        rowIdx += 1

        # Fifth row is ''/Performance - #/No - #/Diagnostic tests - #/
        # Second Tag - #/No - #/''/''  
        performancePct = self.getPctVal(ctx, 'performance', 'Yes')
        planEffectNoPct = self.getPctVal(ctx, 'planEffect', 'No')
        planChangeDiagTest = self.getPctVal(ctx, 'planText', 
                                            unicode('Diagnostic tests'))
        (secondTagEntry, tagnameIdx) = self.getTagEntry(ctx, tagnames, 
                                                        tagnameIdx)
        commBiasNoPct = self.getPctVal(ctx, 'commBias', 'No')

        secondCommBiasComment = '' if (rowIdx > len(commBiasComments) - 1) \
                                   else commBiasComments[rowIdx]

        wr.writerow(['', 'Performance - ' + performancePct, 
                     'No - ' + planEffectNoPct,
                     'Diagnostic tests - ' + planChangeDiagTest,
                     secondTagEntry, 'No - ' + commBiasNoPct,
                     secondCommBiasComment])

        rowIdx += 1

        # Sixth row is ''/Unsure - #/''/Treatment plan - #/Third Tag - #/
        # Unsure - #/''/''
        competenceUnsurePct = self.getPctVal(ctx, 'competence', 'Unsure')
        performanceUnsurePct = self.getPctVal(ctx, 'performance', 'Unsure')
        unsurePct = round(float(competenceUnsurePct[:-1]) \
                    + float(performanceUnsurePct[:-1]), 2)
        planChangeTreatPlan = self.getPctVal(ctx, 'planText', 
                                             unicode('Treatment plan'))
        (thirdTagEntry, tagnameIdx) = self.getTagEntry(ctx, tagnames, 
                                                       tagnameIdx)
        commBiasUnsurePct = self.getPctVal(ctx, 'commBias', 'Unsure')

        thirdCommBiasComment = '' if (rowIdx > len(commBiasComments) - 1) \
                                  else commBiasComments[rowIdx]

        wr.writerow(['', 'Unsure - ' + '%.2f' % unsurePct + '%', '',
                     'Treatment plan - ' + planChangeTreatPlan,
                     thirdTagEntry, 'Unsure - ' + commBiasUnsurePct,
                     thirdCommBiasComment])

        rowIdx += 1

        # Seventh row is ''/''/''/'Other (Please explain)'/Fourth tag - #/
        #
        (fourthTagEntry, tagnameIdx) = self.getTagEntry(ctx, tagnames,
                                                        tagnameIdx)
        wr.writerow(['', '', '', 'Other (Please explain) ', fourthTagEntry])

        while (rowIdx < maxNumRows):
            (tagEntry, tagnameIdx) = self.getTagEntry(ctx, tagnames,
                                                            tagnameIdx)
            wr.writerow(['', '', '', 'Other (Please explain) ', tagEntry])
            rowIdx += 1


        # Column A
        columnA = ['Report Timeframe: ' + startSubjRds + ' - ' + endSubjRds, 'Overall Evaluation Participants N = ']

        # Column B
        competencePct = self.getPctVal(ctx, 'competence', 'Yes')
        performancePct = self.getPctVal(ctx, 'performance', 'Yes')
        competenceUnsurePct = self.getPctVal(ctx, 'competence', 'Unsure')
        performanceUnsurePct = self.getPctVal(ctx, 'performance', 'Unsure')
        unsurePct = round(float(competenceUnsurePct[:-1]) \
                     + float(performanceUnsurePct[:-1]), 2)
        columnB = ['', str(ctx['numUsers']), 'Conducting this search will result in a change in my:', 
                   'Competence - ' + competencePct, 'Performance - ' + performancePct,
                   'Unsure - ' + '%.2f' % unsurePct + '%']

        # Column C
        planEffectPct = self.getPctVal(ctx, 'planEffect', 'Yes')
        planEffectNoPct = self.getPctVal(ctx, 'planEffect', 'No')
        columnC = ['', '', 'Did this information change your clinical plan?',
                   'Yes - ' + planEffectPct, 'No - ' + planEffectNoPct]

        # Column D
        planChangeDiffDiag = self.getPctVal(ctx, 'planText',
                                            unicode('Differential diagnosis'))
        planChangeDiagTest = self.getPctVal(ctx, 'planText',
                                            unicode('Diagnostic tests'))
        planChangeTreatPlan = self.getPctVal(ctx, 'planText',
                                             unicode('Treatment plan'))
        planTextOther = ctx['planTextOther']
        nonEmptyPlanTextOther = []
        for text in planTextOther:
            if text != u'':
                nonEmptyPlanTextOther.append(text)
        otherPleaseExplainAdd = '' if (len(nonEmptyPlanTextOther) == 0) else nonEmptyPlanTextOther[0]
        columnD = ['', '', 'If yes, how?', 'Differential diagnosis - ' + planChangeDiffDiag,
                   'Diagnostic tests - ' + planChangeDiagTest, 'Treatment plan - ' + planChangeTreatPlan,
                   'Other (Please explain)' + otherPleaseExplainAdd]
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
        commBiasYesPct = self.getPctVal(ctx, 'commBias', 'Yes')
        commBiasNoPct = self.getPctVal(ctx, 'commBias', 'No')
        commBiasUnsurePct = self.getPctVal(ctx, 'commBias', 'Unsure')

        columnF = ['', '', 'Did you perceive commercial bias in the content?',
                   'Yes - ' + commBiasYesPct, 'No - ' + commBiasNoPct, 
                   'Unsure - ' + commBiasUnsurePct]
        
        # Column G
        columnG = ['', '', 'If yes, explain']

        # Grab the comments list of commercial bias
        commBiasComments = self.calcResponseStats(qset, 'commercialBias')[1]
        columnG += commBiasComments

        # Column H
        columnH = ['', '', 'Please provide any feedback/comments regarding the articles, or the overall system effectiveness']

        startReportDate = datetime(2017, 10, 1)
        entrySpecific = UserFeedback.objects.filter(entry__isnull=False, created__gte=startReportDate, created__lte=endReportDate).order_by('created')
        general = UserFeedback.objects.filter(entry__isnull=True, created__gte=startReportDate, created__lte=endReportDate).order_by('created')

        generalIdx = 0
        entrySpecificIdx = 0

        while (generalIdx < len(general) and entrySpecificIdx < len(entrySpecific)):
            if (general[generalIdx].created < entrySpecific[entrySpecificIdx].created):
                generalComment = general[generalIdx]
                columnH.append(generalComment.message)
                generalIdx += 1
            else:
                entry = entrySpecific[entrySpecificIdx]
                if ("https://" in entry.message or "http://" in entry.message):
                    columnH.append(entry.message)
                entrySpecificIdx += 1


        if (generalIdx >= len(general)):
            while (entrySpecificIdx < len(entrySpecific)):
                entry = entrySpecific[entrySpecificIdx]
                if ("https://" in entry.message or "http://" in entry.message):
                    columnH.append(entry.message)
                entrySpecificIdx += 1

        if (entrySpecificIdx >= len(entrySpecific)):
            while (generalIdx < len(general)):
                generalComment = general[generalIdx]
                columnH.append(generalComment.message)
                generalIdx += 1

        print columnH

        maxLength = max(len(columnA), len(columnB), len(columnC), len(columnD), 
                        len(columnE), len(columnF), len(columnG), len(columnH))


        # to get general feedback, set entry__isnull=True
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
        rowBased = zip(*columnBased)

        for row in rowBased:
          print row
          wr.writerow(row)
        

        '''
        wr.writerow([''])
        wr.writerow(['Change In Competence'])
        for competence in ctx['competence']:
            wr.writerow([competence['value'], '%.2f' % competence['pct'] + '%'])
        wr.writerow([''])
        wr.writerow(['Change in Performance'])
        for performance in ctx['performance']:
            wr.writerow([performance['value'], '%.2f' % performance['pct'] + '%'])
        wr.writerow([''])
        wr.writerow(['Change in Clinical Plan?'])
        for planEffect in ctx['planEffect']:
            wr.writerow([planEffect['value'], '%.2f' % planEffect['pct'] + '%'])
        wr.writerow([''])
        wr.writerow(['If Yes, How?'])
        for planText in ctx['planText']:
            wr.writerow([planText['value'], '%.2f' % planText['pct'] + '%'])
        wr.writerow([''])
        wr.writerow(['Other changes to Clinical Plan'])
        # without the check that len of element is > 0, strange output is created
        # in attachment csv
        for planTextOther in ctx['planTextOther']:
            if (len(planTextOther) > 0):
                wr.writerow([planTextOther])
        wr.writerow([''])
        wr.writerow(['Commercial Bias In Content'])
        for commBias in ctx['commBias']:
            wr.writerow([commBias['value'], '%.2f' % commBias['pct'] + '%'])
        wr.writerow([''])
        wr.writerow(['Specialty Tags'])
        for tag in ctx['tags']:
            wr.writerow([tag['tagname'], '%.2f' % tag['pct'] + '%'])
        wr.writerow([''])
        wr.writerow(['For what clinical information were you searching?'])
        for description in ctx['descriptions']:
            wr.writerow([description])
        wr.writerow([''])
        wr.writerow(['Feedback'])
        wr.writerow(['None in this period'])
        '''
        return csvfile

    def handle(self, *args, **options):
        # get brcme entries
        now = timezone.now()
        qset, profiles, startDate, endDate = self.getEntries(now)
        # profiles for the distinct users in qset
        profilesById = dict()
        for p in profiles:
            profilesById[p.pk] = p
        results = []
        for m in qset:
            #print "other m: ", m, " m.entry: ", m.entry, " m.entry.user: ", m.entry.user
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
        to_emails = [t[1] for t in settings.MANAGERS] # list of emails
        to_emails.extend(TUFTS_RECIPIENTS)
        to_emails = ["logicalmath333@gmail.com"]
        subject = "Orbit Quarterly Report ({0}-{1})".format(startSubjRds, endSubjRds)
        reportFileName = 'orbit-report-{0}-{1}.csv'.format(startRds, endRds)
        #
        # data for context
        #
        planEffectStats, planTextStats, planTextOther = self.calcPlanStats(qset)
        print "qset: ", qset
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
                from_email=from_email)
        msg.content_subtype = 'html'

        # summary of stats csv attachment
        summaryCsvFile = self.createSummaryCsv(ctx, qset)
        summary = summaryCsvFile.getvalue()
        summaryFileName = 'orbit-summary-{0}-{1}.csv'.format(startRds, endRds)

        msg.attach(reportFileName, cf, 'application/vnd.ms-excel')
        msg.attach(summaryFileName, summary, 'application/vnd.ms-excel')
        try:
            msg.send()
        except SMTPException as e:
            logger.exception('makeTuftsReport send email failed')
        else:
            logger.info('makeTuftsReport send email done')
