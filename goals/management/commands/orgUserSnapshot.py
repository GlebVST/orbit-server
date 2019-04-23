import logging
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from users.models import User, Profile, Organization, OrgMember, OrgAgg, StateLicense
from goals.models import *

logger = logging.getLogger('mgmt.goals')

class Command(BaseCommand):
    help = "Recompute OrgMember snapshot data."

    def handleUser(self, u, fkwargs):
        userdata = {} # null, plus key for each stateid in user's profile
        profile = u.profile
        stateids = profile.stateSet
        sl_qset = StateLicense.objects.getLatestSetForUser(u)
        userdata[None] = UserGoal.objects.compute_userdata_for_admin_view(u, fkwargs, sl_qset)
        for stateid in stateids:
            userdata[stateid] = UserGoal.objects.compute_userdata_for_admin_view(u, fkwargs, sl_qset, stateid)
        return userdata

    def handle(self, *args, **options):
        gts = GoalType.objects.getCreditGoalTypes()
        fkwargs = {
            'valid': True,
            'goal__goalType__in': gts,
            'is_composite_goal': False,
        }
        orgs = Organization.objects.all().order_by('id')
        for org in orgs:
            if not org.activateGoals:
                continue
            if not org.orgmembers.exists():
                continue
            logger.info('Compute user snapshot for org: {0}'.format(org))
            members = org.orgmembers \
                    .filter(removeDate__isnull=True, pending=False) \
                    .order_by('id')
            total_cme_gap_expired = 0
            total_licenses_expired = 0
            total_cme_gap_expiring = 0
            total_licenses_expiring = 0
            for m in members:
                now = timezone.now()
                userdata = self.handleUser(m.user, fkwargs)
                m.snapshot = userdata
                m.snapshotDate = now
                m.save(update_fields=('snapshot', 'snapshotDate'))
                total_cme_gap_expired += userdata['expired'][CME_GAP]
                total_licenses_expired += userdata['expired'][LICENSES]
                total_cme_gap_expiring += userdata['expiring'][CME_GAP]
                total_licenses_expiring += userdata['expiring'][LICENSES]
            # update OrgAgg
            today = timezone.now().date()
            qs = OrgAgg.objects.filter(organization=org, day=today)
            if qs.exists():
                orgagg = qs[0]
                # update existing entry
                orgagg.cme_gap_expired = total_cme_gap_expired
                orgagg.cme_gap_expiring = total_cme_gap_expiring
                orgagg.licenses_expired = total_licenses_expired
                orgagg.licenses_expiring = total_licenses_expiring
                orgagg.save()
                logger.info('Updated OrgAgg for {0.organization} {0.day}'.format(orgagg))
            else:
                orgagg = OrgAgg.objects.create(
                    organization=org,
                    day=today,
                    cme_gap_expired = total_cme_gap_expired,
                    cme_gap_expiring = total_cme_gap_expiring,
                    licenses_expired = total_licenses_expired,
                    licenses_expiring = total_licenses_expiring
                )
                logger.info('Created OrgAgg for {0.organization} {0.day}'.format(orgagg))
