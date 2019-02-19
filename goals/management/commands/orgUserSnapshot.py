import logging
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from users.models import User, Profile, Organization, OrgMember, StateLicense
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
            if not org.orgmembers.exists():
                continue
            logger.info('Compute user snapshot for org: {0}'.format(org))
            members = org.orgmembers \
                    .filter(removeDate__isnull=True, pending=False) \
                    .order_by('id')
            for m in members:
                if not m.user.profile.verified:
                    # user has not officially joined yet
                    continue
            userdata = self.handleUser(m.user, fkwargs)
            m.snapshot = userdata
            m.save(update_fields=('snapshot',))
