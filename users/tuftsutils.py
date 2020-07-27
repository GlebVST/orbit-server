import logging
import csv
import gspread
from io import StringIO
from django.db.models import Q, Subquery
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

def formatRange(arr):
    """Transform a list [a,b,c,...] into: [[a,],[b,],[c,],...]
    This is used to update cells of a single column in the gsheet
    Returns: list of lists
    """
    return [[v,] for v in arr]

def cleanDescription(d):
    d2 = d
    if J in d:
        idx = d.index(J)
        d2 = d[0:idx]
    return d2

class BaseReport:
    PROFILE_FIELDS = (
        'LastName',
        'FirstName',
        'Degree',
        'NPI #',
    )
    ENTRY_FIELDS = (
        'Search Date',
        'Credit Earned',
        'Attendee Type (Physician or Other)',
        'TopicSearched',
        'Article/Website Consulted',
    )

    def __init__(self, startDate, endDate, cred_fpath, docid):
        """
        Args:
            startDate: utc datetime
            endDate: utc datetime
            cred_path: str filepath to the credentials file for google-auth
            docid: document key/id - this Google Doc should already exist and shared
                with the service account email listed in the credentials file.
        """
        self.startDate = startDate
        self.endDate = endDate
        msg = "Report date range: {0.startDate:%Y-%m-%d} to {0.endDate:%Y-%m-%d}".format(self)
        logger.info(msg)
        gc = gspread.service_account(cred_fpath)
        self.sheet = gc.open_by_key(docid).sheet1


    def initializeSummarySheet(self):
        """Clear the sheet and initialize with the heading values
        """
        self.sheet.clear()
        # Column A
        self.sheet.update('A1', 'Quarterly Report:')
        self.sheet.update('A2', 'Overall Evaluation Participants N =')
        self.sheet.update('A3', 'Total # of responses =')
        self.sheet.update('A4', 'For what clinical information were you searching?')
        
        # Column B
        self.sheet.update('B1', 'Date Range (actual dates)')
        self.sheet.update('B4', 'Conducting this search will result in a change in my:')
        # Column C
        self.sheet.update('C4', 'Did this information change your clinical plan (Diagnosis/Treatment)? ')
        # Column D
        self.sheet.update('D4', 'If yes, how?')
        # Column E
        self.sheet.update('E4', 'Select relevant specialty tags to categorize this credit ')
        # Column F
        self.sheet.update('F4', 'Did you perceive commercial bias in the content?')
        # Column G
        self.sheet.update('G4', 'If yes,  explain.')
        # Column H
        self.sheet.update('H4', 'Please provide any feedback/comments regarding the articles, or the overall system effectiveness')


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
        #print(self.entries.query)
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

    def calcNumUsers(self):
        """Calculate distinct number of users from self.entries
        Note: this value can be less than profiles.count because
        not every eligible profile may have an entry for this period.
        """
        userids = set([])
        for entry in self.entries:
            userids.add(entry.user.pk)
        return len(userids)

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
            mapped_value = RESPONSE_MAP[v]
            stats.append(dict(value=mapped_value, count=cnt, pct=pct))
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
            mapped_value = RESPONSE_MAP[v]
            planEffectStats.append(dict(value=mapped_value, count=cnt, pct=pct))
        # planText: partition into keyed responses vs Other
        planTextDict = {
            BrowserCme.DIFFERENTIAL_DIAGNOSIS: 0,
            BrowserCme.TREATMENT_PLAN: 0,
            BrowserCme.DIAGNOSTIC_TEST: 0
        }
        planTextOther = []
        for m in qset:
            pt = m.planText.strip()
            if pt in planTextDict:
                # keyed response
                planTextDict[pt] += 1
            elif pt:
                planTextOther.append(pt) # non-empty other values
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
            for tags whose percentage of total is at least 1 percent.
            The remaining tags are combined into OTHER (cnt/pct).
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
        tag_stats = [] # sorted by tagname (w. OTHER at the end). filter by pct >=1
        for tagname in sorted(counts):
            if tagname == OTHER:
                continue
            tagpct = counts[tagname]['pct']
            if tagpct < 1:
                continue
            tag_stats.append(dict(
                tagname=tagname,
                pct=tagpct,
                count=counts[tagname]['count']
            ))
        # add OTHER at the end
        tagname = OTHER
        tag_stats.append(dict(
            tagname=tagname,
            pct=counts[tagname]['pct'],
            count=counts[tagname]['count']
        ))
        return tag_stats

    def getEntryDescriptions(self):
        """Clean entry description from self.entries
        Returns: list of strs (duplicates removed)
        """
        qset = self.entries
        descriptions = []
        # Note: distinct removes duplicates
        vqset = qset.values_list('description', flat=True).distinct().order_by('description')
        for v in vqset:
            descr = v.strip()
            descr = cleanDescription(descr)
            descriptions.append(descr)
        return descriptions

    def makeReportData(self):
        """Calculate report data for participant report
        This should be called after getEntries is called.
        Returns: list of dicts w. keys from PROFILE_FIELDS + ENTRY_FIELDS
        """
        cls = self.__class__
        results = []
        all_fields = cls.PROFILE_FIELDS + cls.ENTRY_FIELDS
        for (entry, brcme) in zip(self.entries, self.qset_brcme):
            user = entry.user
            profile = self.profilesById[user.pk]
            d = dict()
            for k in all_fields:
                d[k] = ''
            d['id'] = profile.pk
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
        cls = self.__class__
        output = StringIO()
        out_fields = cls.PROFILE_FIELDS + cls.ENTRY_FIELDS
        #print(out_fields)
        writer = csv.DictWriter(output, delimiter=',', fieldnames=out_fields, extrasaction='ignore')
        writer.writeheader()
        for row in results:
            writer.writerow(row)
        cf = output.getvalue() # to be used as attachment for EmailMessage
        return cf

    def getEntryFeedback(self):
        """Get list of entry-specific UserFeedback messages having either hasBias or UnfairContent = true.
        Returns: list of strs
        """
        qf = Q(hasBias=True) | Q(hasUnfairContent=True)
        fkwargs = dict(
            entry__isnull=False,
            created__gte=self.startDate,
            created__lte=self.endDate
        )
        qs = UserFeedback.objects.filter(qf, **fkwargs).order_by('created')
        data = [m.message for m in qs]
        return data

    def makeContext(self):
        """Returns context dictionary - used by getSummaryCsv
        """
        planEffectStats, planTextStats, planTextOther = self.calcPlanStats()
        (commBiasStats, commBiasComments) = self.calcResponseStats('commercialBias')
        # UserFeedback associated with entries (entrySpecific)
        entryFeedback = self.getEntryFeedback()
        ctx = {
            'startDate': self.startDate,
            'endDate': self.endDate,
            'numEntries': self.entries.count(),
            'tags': self.calcTagStats(),
            'competence': self.calcResponseStats('competence')[0],
            'performance': self.calcResponseStats('performance')[0],
            'commBias': commBiasStats,
            'commBiasComments': commBiasComments,
            'descriptions': self.getEntryDescriptions(),
            'planEffect': planEffectStats,
            'planText': planTextStats,
            'planTextOther': planTextOther,
            'entryFeedback': entryFeedback
        }
        ctx['numUsers'] = self.calcNumUsers()
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


    def createSummaryCsv(self, ctx, startReportDate, endReportDate):
        """Create a summary of the stats in csv format. To be used as an attachment
        Args:
            ctx: dictionary containing the stats
        Returns: StringIO object containing the csv data
        Note: The return value is meant to be included as an email attachment.
          To write result to a local file, use:
          with open('filename.csv', mode='w') as f:
              print(csvfile.getvalue(), file=f)
        """
        self.initializeSummarySheet()
        # string formatted dates
        startSubjRds = startReportDate.strftime('%b/%d/%Y')
        endSubjRds = endReportDate.strftime('%b/%d/%Y')
        START_ROW_IDX = 5 # default start row index for data
        # Column A
        numDescr = len(ctx['descriptions'])
        startIndex = START_ROW_IDX
        if numDescr:
            colRange = 'A{0}:A{1}'.format(startIndex, startIndex+numDescr-1)
            self.sheet.update(colRange, formatRange(ctx['descriptions']))
        else:
            self.sheet.update('A{0}'.format(startIndex), 'No data')

        # Column B
        self.sheet.update('B1', '{0} - {1}'.format(startSubjRds, endSubjRds)) # report date range
        self.sheet.update('B2', ctx['numUsers']) # participant count
        self.sheet.update('B3', ctx['numEntries']) # responses count
        # competence
        key = 'competence'
        competence_str = "Competence - Yes:{0} No:{1} Unsure:{2}".format(
            self.getVal(ctx, key, 'Yes'),
            self.getVal(ctx, key, 'No'),
            self.getVal(ctx, key, 'Unsure')
        )
        self.sheet.update('B5', competence_str)
        # performance
        key = 'performance'
        performance_str = "Performance - Yes:{0} No:{1} Unsure:{2}".format(
            self.getVal(ctx, key, 'Yes'),
            self.getVal(ctx, key, 'No'),
            self.getVal(ctx, key, 'Unsure')
        )
        self.sheet.update('B6', performance_str)

        # Column C
        key = 'planEffect'
        self.sheet.update('C5', 'Yes - {0}'.format(self.getVal(ctx, key, 'Yes')))
        self.sheet.update('C6', 'No - {0}'.format(self.getVal(ctx, key, 'No')))
        self.sheet.update('C7', 'Unsure - {0}'.format(self.getVal(ctx, key, 'Unsure')))

        # Column D
        key = 'planText'
        #self.sheet.update('D5', 'Will change prescription: 0')
        self.sheet.update('D5', 'Will change differential diagnosis: {0}'.format(self.getVal(ctx, key, BrowserCme.DIFFERENTIAL_DIAGNOSIS)))
        self.sheet.update('D6', 'Will change diagnostic tests: {0}'.format(self.getVal(ctx, key, BrowserCme.DIAGNOSTIC_TEST)))
        self.sheet.update('D7', 'Will change treatment plan: {0}'.format(self.getVal(ctx, key, BrowserCme.TREATMENT_PLAN)))
        self.sheet.update('D8', 'Other (please specify):')
        startIdx = 9 # for planTextOther
        # If we have any text in planTextOther, then add it
        num_text = len(ctx['planTextOther'])
        if num_text:
            colRange = 'D{0}:D{1}'.format(startIdx, startIdx+num_text-1)
            self.sheet.update(colRange, formatRange(ctx['planTextOther']))

        # Column E (tags)
        tagStats = ctx['tags']
        tagData = ['{tagname} - {count}'.format(**d) for d in tagStats]
        num_tags = len(tagData)
        startIdx = START_ROW_IDX
        colRange = 'E{0}:E{1}'.format(startIdx, startIdx+num_tags-1)
        self.sheet.update(colRange, formatRange(tagData))

        # Column F (commBias)
        key = 'commBias'
        self.sheet.update('F5', 'Yes - {0}'.format(self.getVal(ctx, key, 'Yes')))
        self.sheet.update('F6', 'No - {0}'.format(self.getVal(ctx, key, 'No')))
        self.sheet.update('F7', 'Unsure - {0}'.format(self.getVal(ctx, key, 'Unsure')))
        
        # Column G (commBiasComments)
        numComments = len(ctx['commBiasComments'])
        if (numComments):
            startIdx = START_ROW_IDX
            colRange = 'G{0}:G{1}'.format(startIdx, startIdx+numComments-1)
            self.sheet.update(colRange, formatRange(ctx['commBiasComments']))

        # Column H (entryFeedback)
        numComments = len(ctx['entryFeedback'])
        if (numComments):
            startIdx = START_ROW_IDX
            colRange = 'H{0}:H{1}'.format(startIdx, startIdx+numComments-1)
            self.sheet.update(colRange, formatRange(ctx['entryFeedback']))

        # get all data
        rowData = self.sheet.get_all_values() # [row1, row2, ...rowN] where row_j is a list
        # write to csv
        csvfile = StringIO()
        wr = csv.writer(csvfile)
        for row in rowData:
            wr.writerow(row)
        return csvfile # StringIO contained in memory


class MainReport(BaseReport):
    """This report is used the makeTuftsReport management command.
    """

    def makeEntryQuerySet(self):
        """
        2020-07-26: This query no longer excludes Internal Medicine users
        """
        entries = super().makeEntryQuerySet()
        #ps_intmed = PracticeSpecialty.objects.get(name=PracticeSpecialty.INT_MED)
        #q_intmed = Profile.objects.filter(specialties=ps_intmed)
        #entries = entries.exclude(user__in=Subquery(q_intmed.values('user')))
        return entries


class IntMedReport(BaseReport):
    """This report is used by the makeTuftsIntMedReport management command. It includes only Internal Medicine users with completed profile
    """

    PROFILE_FIELDS = BaseReport.PROFILE_FIELDS + (
        'ABIMNumber',
        'Birthdate MM/DD'
    )

    def makeEntryQuerySet(self, profiles):
        """Get not-yet-submitted brcme entries for the given profiles.
        It returns all entries (for the given profiles) less than or equal to
        self.endDate that have not yet been submitted.
        Note: this does not use self.startDate.
        Returns: Entry queryset
        """
        fkwargs = dict(
            valid=True,
            entryType=EntryType.objects.get(name=ENTRYTYPE_BRCME),
            submitABIMDate__isnull=True,
            activityDate__lte=self.endDate
        )
        entries = Entry.objects.filter(**fkwargs) \
            .filter(user__in=Subquery(profiles.values('pk')))
        return entries

    def makeEndOfYearEntryQuerySet(self, profiles):
        """The End of Year report includes all entries from
        self.startDate to self.endDate for the given profiles
        and whose submitABIMDate is set (e.g. already submitted
        in a bimonthly report).
        Returns: Entry queryset
        """
        fkwargs = dict(
            valid=True,
            entryType=EntryType.objects.get(name=ENTRYTYPE_BRCME),
            submitABIMDate__isnull=False,
            activityDate__gte=self.startDate,
            activityDate__lte=self.endDate
        )
        entries = Entry.objects.filter(**fkwargs) \
            .filter(user__in=Subquery(profiles.values('pk')))
        return entries

    def getEntries(self, isEndOfYearReport=False):
        """Override method to limit profiles to IntMed users who
        have completed their profile.
        Sets self.entries, self.qset_brcme, self.profiles, and 
            self.profilesById
        """
        self.profiles = Profile.objects.getProfilesForTuftsABIM()
        if not isEndOfYearReport:
            entries = self.makeEntryQuerySet(self.profiles)
        else:
            entries = self.makeEndOfYearEntryQuerySet(self.profiles)
        self.entries = entries.order_by('activityDate', 'pk')
        #print(self.entries.query)
        # get BrowserCme instances for entries
        self.qset_brcme = BrowserCme.objects \
            .select_related('entry') \
            .filter(pk__in=Subquery(entries.values('pk'))) \
            .order_by('entry__activityDate', 'pk')
        # make profilesById
        self.profilesById = dict()
        for p in self.profiles:
            self.profilesById[p.pk] = p

    def makeReportData(self):
        """Add ABIMNumber and Birthdate keys to the data for the participant report.
        """
        results = super().makeReportData()
        for d in results:
            profile = self.profilesById[d['id']]
            d['ABIMNumber'] = profile.ABIMNumber
            if profile.birthDate:
                d['Birthdate MM/DD'] = profile.birthDate.strftime('%m/%d')
        return results

    def updateSubmitDate(self, submitDate):
        """Set submitABIMDate on self.entries
        """
        ret = self.entries.update(submitABIMDate=submitDate)
