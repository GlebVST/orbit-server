import logging
import csv
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
from users.models import User, Profile, Entry, BrowserCme
from pprint import pprint

logger = logging.getLogger('mgmt.tuftsqr')

outputFields = (
    'LastName',
    'FirstName',
    'Degree',
    'NPINumber',
    'Search Date',
    'Credit Earned',
    'Attendee Type',
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
RESPONSE_CHOICES = (
        BrowserCme.RESPONSE_YES,
        BrowserCme.RESPONSE_NO,
        BrowserCme.RESPONSE_UNSURE
)

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
        Returns: list of dicts w. keys: value, count, pct
        """
        num_entries = qset.count()
        stats = []
        clause = '{0}__exact'.format(fieldname)
        for v in RESPONSE_CHOICES:
            filter_kwargs = {clause: v}
            cnt = qset.filter(**filter_kwargs).count()
            pct = 100.0*cnt/num_entries
            stats.append(dict(value=v, count=cnt, pct=pct))
        return stats

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
            print("{0} {1} {2}".format(tagname, tagcount, tagpct))
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

    def calcPlanStats(self, qset):
        return (planTextStats, planTextOther)

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
            user = m.entry.user
            profile = profilesById[user.pk]
            d = dict()
            for k in outputFields:
                d[k] = ''
            d['NPINumber'] = profile.npiNumber
            if profile.isPhysician():
                d['Attendee Type'] = 'Physician'
            else:
                d['Attendee Type'] = 'Other'
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
        cf = output.getvalue()
        reportDate = endDate + timedelta(days=1) # use reportDate instead of now since cmd can be run at any time
        rds = reportDate.strftime('%d%b%Y')
        # create EmailMessage
        from_email = settings.EMAIL_FROM
        to_email = [t[1] for t in settings.MANAGERS] # list of emails
        subject = "Orbit Quarterly Report {0}".format(eds)
        fileName = 'OrbitQuarterlyReport_{0}.csv'.format(eds)
        ctx = {
            'startDate': startDate,
            'endDate': endDate,
            'numUsers': len(profiles),
            'tags': self.calcTagStats(qset),
            'competence': self.calcResponseStats(qset, 'competence'),
            'performance': self.calcResponseStats(qset, 'performance'),
            'commBias': self.calcResponseStats(qset, 'commercialBias'),
            'planEffectYes': planEffectStats[BrowserCme.RESPONSE_YES],
            'planEffectNo': planEffectStats[BrowserCme.RESPONSE_NO],
            'planText': planTextStats,
            'planTextOther': planTextOther,
            'descriptions': descriptions
        }
        message = get_template('email/tufts_quarterly_report.html').render(ctx)
        msg = EmailMessage(
                subject,
                message,
                to=to_email,
                from_email=from_email)
        msg.content_subtype = 'html'
        msg.attach(fileName, cf, 'application/vnd.ms-excel')
        try:
            msg.send()
        except SMTPException as e:
            logger.exception('makeTuftsReport send email failed')
        else:
            logger.info('makeTuftsReport send email done')
