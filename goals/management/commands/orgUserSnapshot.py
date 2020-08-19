import logging
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from users.models import (
        User,
        Profile,
        Organization,
        OrbitCmeOffer,
        OrgMember,
        OrgAgg,
        StateLicense
    )
from goals.models import *

logger = logging.getLogger('mgmt.goals')

ARTICLE_LOOKBACK = 30 # number of days in time window
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
        # Get orgs that qualify as active Enterpise orgs
        orgs = Organization.objects.filter(activateGoals=True, computeTeamStats=True).order_by('id')
        for org in orgs:
            members = org.orgmembers \
                    .filter(removeDate__isnull=True, pending=False) \
                    .order_by('id')
            if not members.exists(): # no active members
                continue
            logger.info('Compute user snapshot for org: {0}'.format(org))
            total_cme_gap_expired = 0
            total_licenses_expired = 0
            total_cme_gap_expiring = 0
            total_licenses_expiring = 0
            for m in members:
                now = timezone.now()
                minStartDate = now - timedelta(days=ARTICLE_LOOKBACK)
                maxEndDate = now + timedelta(days=1)
                userdata = self.handleUser(m.user, fkwargs)
                m.snapshot = userdata
                m.snapshotDate = now
                # compute articles read over time window
                m.numArticlesRead30, m.cmeRedeemed30 = OrbitCmeOffer.objects.sumArticlesRead(m.user, minStartDate, maxEndDate)
                m.save(update_fields=('numArticlesRead30', 'cmeRedeemed30', 'snapshot', 'snapshotDate'))
                udata = userdata[None] # counting over all states
                total_cme_gap_expired += udata['expired'][CME_GAP]
                total_licenses_expired += udata['expired'][LICENSES]
                total_cme_gap_expiring += udata['expiring'][CME_GAP]
                total_licenses_expiring += udata['expiring'][LICENSES]
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
