import logging
import pytz
from datetime import datetime
from dateutil.relativedelta import *
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db.models import Q, Subquery
from django.utils import timezone
from users.models import Organization, OrgMember, OrgAgg, Profile, Degree, Entry

logger = logging.getLogger('mgmt.orgstat')

class Command(BaseCommand):
    help = "Compute and update various stats for enterprise orgs. This should be called by a daily cron task."

    def handle(self, *args, **options):
        # get distinct orgs
        orgids = OrgMember.objects.all().values_list('organization', flat=True).distinct()
        for orgid in orgids:
            org = Organization.objects.get(pk=orgid)
            firstMember = org.orgmembers.all().order_by('created')[0]
            startDate = firstMember.created
            #self.stdout.write('StartDate: {0}'.format(startDate))
            filter_kwargs = {
                'user__profile__organization': org,
                'valid': True
            }
            if org.creditEndDate:
                # if credits have been computed before, then just add credits from entries created since the last calculation
                filter_kwargs['created__gt'] = org.creditEndDate
            entries = Entry.objects.select_related('entryType', 'user__profile').filter(**filter_kwargs).order_by('id')
            credits = 0
            saveOrg = False
            now = timezone.now()
            for entry in entries:
                credits += entry.getCredits()
            credits = float(credits)
            if credits:
                org.credits += credits
                org.creditEndDate = now
                saveOrg = True
            if not org.creditStartDate:
                org.creditStartDate = startDate
                saveOrg = True
            if saveOrg:
                org.save(update_fields=('credits', 'creditStartDate', 'creditEndDate'))
            #self.stdout.write('Org {0.code} credits {0.credits} until EndDate: {0.creditEndDate}'.format(org))
            # provider stat: current vs end-of-prior-month
            providerStat = dict()
            degrees = Degree.objects.all()
            for d in degrees:
                providerStat[d.abbrev] = {'count': 0, 'lastCount': 0, 'diff': 0}
            # filter out pending org users
            members = org.orgmembers.filter(removeDate__isnull=True, pending=False)
            # Per request of Ram: do not filter by profile.verified. Even if false, should still be included in the count.
            profiles = Profile.objects.filter(user__in=Subquery(members.values('user'))).only('user','degrees').prefetch_related('degrees')
            for profile in profiles:
                d = profile.degrees.all()[0]
                providerStat[d.abbrev]['count'] += 1
            # get datetime of end of last month
            cutoffDate = datetime(now.year, now.month, 1, 23, 59, 59, tzinfo=pytz.utc) - relativedelta(days=1)
            # members existing at that time
            members = org.orgmembers.filter(
                Q(removeDate__isnull=True) | Q(removeDate__gte=cutoffDate),
                created__lte=cutoffDate,
                pending=False
            )
            profiles = Profile.objects.filter(user__in=Subquery(members.values('user'))).only('user','degrees').prefetch_related('degrees')
            for profile in profiles:
                d = profile.degrees.all()[0]
                providerStat[d.abbrev]['lastCount'] += 1
            # calculate diff percentage
            for abbrev in providerStat:
                count = providerStat[abbrev]['count']
                lastCount = providerStat[abbrev]['lastCount']
                diff = 0
                if lastCount:
                    diff = (count - lastCount)*1.0/lastCount
                else:
                    diff = count
                providerStat[abbrev]['diff'] = diff*100
            org.providerStat = providerStat
            org.save(update_fields=('providerStat',))
            logger.info('Updated org {0}'.format(org))
            # update OrgAgg user stats
            orgAgg = OrgAgg.objects.compute_user_stats(org)
            logger.info('Saved OrgAgg {0.pk} {0.day}'.format(orgAgg))
