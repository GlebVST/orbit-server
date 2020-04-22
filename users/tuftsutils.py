import logging
import csv
from io import StringIO
import io
import pytz
from django.conf import settings
from django.db.models import Subquery
from django.utils import timezone
from users.models import (
    ENTRYTYPE_BRCME,
    User,
    Profile,
    PracticeSpecialty,
    Entry,
    EntryType,
    BrowserCme,
    UserFeedback
)
logger = logging.getLogger('mgmt.tufts')

TUFTS_RECIPIENTS = [
    'Mirosleidy.Tejeda@tufts.edu',
    'Karin.Pearson@tufts.edu',
    'Katelyn.McBurney@tufts.edu',
    'Karlee.Pedemonti@tufts.edu'
]

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

OUTPUT_FIELDS = (
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
    BrowserCme.RESPONSE_UNSURE
)
PLAN_TEXT_CHOICES = (
    BrowserCme.DIFFERENTIAL_DIAGNOSIS,
    BrowserCme.TREATMENT_PLAN,
    BrowserCme.DIAGNOSTIC_TEST
)
J = ': American Journal of Roentgenology'

def cleanDescription(d):
    d2 = d
    if J in d:
        idx = d.index(J)
        d2 = d[0:idx]
    return d2

class BaseReport:

    def __init__(self, startDate, endDate):
        """
        Args:
            startDate: utc datetime
            endDate: utc datetime
        """
        self.startDate = startDate
        self.endDate = endDate
        msg = "Report date range: {0.startDate:%Y-%m-%d} to {0.endDate:%Y-%m-%d}".format(self)
        logger.info(msg)

    def makeEntryQuerySet(self):
        """Get and return Entry queryset for self.startDate,self.endDate range.
        This queryset does not have an order_by, so caller can add more clauses as needed
        Returns: Entry queryset filtered for brcme entries in date range with IGNORE_USERS omitted
        """
        q_omit_users = User.objects.filter(email__in=IGNORE_USERS).values_list('id', flat=True)
        omit_userids = list(q_omit_users)
        fkwargs = dict(
            valid=True,
            entryType=EntryType.objects.get(name=ENTRYTYPE_BRCME),
            activityDate__gte=self.startDate,
            activityDate__lte=self.endDate
        )
        # exclude specific groups of users
        entries = Entry.objects.filter(**fkwargs).exclude(user__in=omit_userids)
        return entries

    def getEntries(self):
        """Get brcme entries and distinct profiles from the given entries queryset
        Sets self.entries, self.qset_brcme, self.profiles, and 
            self.profilesById
        """
        entries = self.makeEntryQuerySet()
        self.entries = entries.order_by('activityDate', 'pk')
        print(self.entries.query)
        # get BrowserCme instances for entries
        self.qset_brcme = BrowserCme.objects \
            .select_related('entry') \
            .filter(pk__in=Subquery(entries.values('pk'))) \
            .order_by('entry__activityDate', 'pk')
        # get distinct profiles in entries
        self.profiles = Profile.objects.filter(user__in=Subquery(entries.values('user'))).order_by('pk')
        self.profilesById = dict()
        for p in self.profiles:
            self.profilesById[p.pk] = p

    def calcResponseStats(self, fieldname):
        """Calculate YES/NO/UNSURE stats for the given field.
        Uses self.qset_brcme
        Args:
            fieldname: one of: competence/performance/commercialBias
        Returns: a tuple of
        (1) list of dicts w. keys: value, count, pct
        (2) list of comments for that particular field (if any)
        """
        qset = self.qset_brcme
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


    def calcPlanStats(self):
        """Calculate stats on planEffect and planText
        Uses self.qset_brcme
        Returns: tuple
            planEffectStats: list of dicts w. keys value, count, pct
            planTextStats: list of dicts w. keys value, count, pct
            planTextOther: list of strs
        """
        qset = self.qset_brcme
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

    def calcTagStats(self):
        """Calculate tag statistics from self.entries queryset
        Returns: list of dicts w. keys: tagname, pct, count
        """
        qset = self.entries
        counts = {
            OTHER: {'count': 0, 'pct': 0}
        }
        for entry in qset:
            tags = entry.tags.all()
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

    def getEntryDescriptions(self):
        """Clean entry description from self.entries
        Returns: list of strs
        """
        qset = self.entries
        descriptions = []
        vqset = qset.values_list('description', flat=True).distinct().order_by('description')
        for v in vqset:
            descr = v.strip()
            if descr.startswith('www.') and (descr.endswith('.org') or descr.endswith('.gov') or descr.endswith('.com')):
                continue
            descr = cleanDescription(descr)
            if not descr:
                continue
            descriptions.append(descr)
        return descriptions

    def makeReportData(self):
        """Calculate report data
        Returns: list of dicts w. keys from OUTPUT_FIELDS
        """
        self.getEntries()
        results = []
        for (entry, brcme) in zip(self.entries, self.qset_brcme):
            user = entry.user
            profile = self.profilesById[user.pk]
            d = dict()
            for k in OUTPUT_FIELDS:
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
            d['Search Date'] = entry.activityDate.strftime('%Y-%m-%d')
            d['Credit Earned'] = str(brcme.credits)
            d['TopicSearched'] = entry.description.encode("ascii", errors="ignore").decode()
            d['Article/Website Consulted'] = brcme.url
            results.append(d)
        return results

    def createReportCsv(self, results):
        """Returns csv file as StringIO""" 
        output = StringIO()
        writer = csv.DictWriter(output, delimiter=',', fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in results:
            writer.writerow(row)
        cf = output.getvalue() # to be used as attachment for EmailMessage
        return cf

    def makeContext(self):
        """Returns context dictionary - used by getSummaryCsv
        """
        planEffectStats, planTextStats, planTextOther = self.calcPlanStats()
        (commBiasStats, commBiasComments) = self.calcResponseStats('commercialBias')
        ctx = {
            'startDate': self.startDate,
            'endDate': self.endDate,
            'numUsers': self.profiles.count(),
            'tags': self.calcTagStats(),
            'competence': self.calcResponseStats('competence')[0],
            'performance': self.calcResponseStats('performance')[0],
            'commBias': commBiasStats,
            'commBiasComments': commBiasComments,
            'descriptions': self.getEntryDescriptions(),
            'planEffect': planEffectStats,
            'planText': planTextStats,
            'planTextOther': planTextOther,
        }
        return ctx

    def getVal(self, ctx, key, subvalue, subkey = 'value'):
        """Helper function used getSummaryCsv.
        Create a string for displaying counts. This is the
        number of BrowserCme entries. The dict in ctx that has
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

    def createSummaryCsv(self, ctx, startReportDate, endReportDate):
        """Create a summary of the stats in csv format. To be used as an attachment
        Args:
            ctx: dictionary containing the stats
        Returns: stats in csv format
        """
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
        planChangeDiffDiag = self.getVal(ctx, 'planText', 'Differential diagnosis')
        planChangeDiagTest = self.getVal(ctx, 'planText', 'Diagnostic tests')
        planChangeTreatPlan = self.getVal(ctx, 'planText', 'Treatment plan')
        # Determine if we will need add any text to the 'Other (Please explain)'
        # cell and add it if we have any text in planTextOther
        planTextOther = ctx['planTextOther']
        nonEmptyPlanTextOther = []
        for text in planTextOther:
            if text != '':
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
        columnG += ctx['commBiasComments']

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
        csvfile = StringIO()
        wr = csv.writer(csvfile)
        rowBased = zip(*columnBased)
        for row in rowBased:
            wr.writerow(row)
        return csvfile


class MainReport(BaseReport):
    """This report is used the makeTuftsReport management command.
    This report excludes users with Internal Medicine specialty
    """

    def makeEntryQuerySet(self):
        """Add exclude clause to omit Internal Medicine users"""
        entries = super().makeEntryQuerySet()
        ps_intmed = PracticeSpecialty.objects.get(name=PracticeSpecialty.INT_MED)
        q_intmed = Profile.objects.filter(specialties=ps_intmed)
        entries = entries.exclude(user__in=Subquery(q_intmed.values('user')))
        return entries


class IntMedReport(BaseReport):
    """This report is used by the makeTuftsIntMedReport management command. It includes only Internal Medicine users with completed profile
    """
    
    def makeEntryQuerySet(self, profiles):
        """Get not-yet-submitted brcme entries for the given profiles. Note: this does not use self.startDate/endDate. It returns all
        entries (for the given profiles) that have not yet been
        submitted.
        Returns: Entry queryset
        """
        fkwargs = dict(
            valid=True,
            entryType=EntryType.objects.get(name=ENTRYTYPE_BRCME),
            submitABIMDate__isnull=True
        )
        entries = Entry.objects.filter(**fkwargs) \
            .filter(user__in=Subquery(profiles.values('pk')))
        return entries

    def getEntries(self):
        """Override method to limit profiles to IntMed users who
        have completed their profile.
        Sets self.entries, self.qset_brcme, self.profiles, and 
            self.profilesById
        """
        self.profiles = Profile.objects.getProfilesForTuftsABIM()
        entries = self.makeEntryQuerySet(self.profiles)
        self.entries = entries.order_by('activityDate', 'pk')
        print(self.entries.query)
        # get BrowserCme instances for entries
        self.qset_brcme = BrowserCme.objects \
            .select_related('entry') \
            .filter(pk__in=Subquery(entries.values('pk'))) \
            .order_by('entry__activityDate', 'pk')
        # make profilesById
        self.profilesById = dict()
        for p in self.profiles:
            self.profilesById[p.pk] = p
