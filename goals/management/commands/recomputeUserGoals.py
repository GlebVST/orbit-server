import logging
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db.utils import IntegrityError
from django.utils import timezone
from users.models import User, Profile
from goals.models import GoalType, UserGoal

logger = logging.getLogger('mgmt.goals')

class Command(BaseCommand):
    help = "Recompute all UserGoals to update their status."

    def handle(self, *args, **options):
        licenseGoalType = GoalType.objects.get(name=GoalType.LICENSE)
        cmeGoalType = GoalType.objects.get(name=GoalType.CME)
        srcmeGoalType = GoalType.objects.get(name=GoalType.SRCME)
        # get distinct users
        users = UserGoal.objects.all().values_list('user', flat=True).distinct().order_by('user')
        profiles = Profile.objects.filter(user_id__in=users).order_by('user_id')
        now = timezone.now()
        for profile in profiles:
            user = profile.user
            self.stdout.write('Process user {0}'.format(user))
            numProfileSpecs = len(profile.specialtySet)
            total_goals = 0
            complianceDict = {
                    UserGoal.NON_COMPLIANT: 0,
                    UserGoal.INCOMPLETE_PROFILE: 0,
                    UserGoal.INCOMPLETE_LICENSE: 0,
                    UserGoal.MARGINAL_COMPLIANT: 0,
                    UserGoal.COMPLIANT: 0
            }
            # recompute user license goals.
            qset = user.usergoals.select_related('goal','license').filter(goal__goalType=licenseGoalType).exclude(status=UserGoal.EXPIRED)
            for m in qset:
                m.recompute()
                complianceDict[m.compliance] += 1
                total_goals += 1
            # recompute individual cmegoals
            qset = user.usergoals.select_related('goal').filter(goal__goalType=cmeGoalType, is_composite_goal=False).order_by('pk')
            for m in qset:
                try:
                    m.recompute(numProfileSpecs)
                except IntegrityError as e:
                    pass
                else:
                    complianceDict[m.compliance] += 1
                    total_goals += 1
            # recompute composite cmegoals (AFTER individuals have been recomputed)
            qset = user.usergoals.select_related('goal').filter(goal__goalType=cmeGoalType, is_composite_goal=True).prefetch_related('constituentGoals').order_by('pk')
            for m in qset:
                try:
                    m.recompute()
                except IntegrityError as e:
                    pass
                else:
                    complianceDict[m.compliance] += 1
                    total_goals += 1
            # recompute individual srcmegoals
            qset = user.usergoals.select_related('goal').filter(goal__goalType=srcmeGoalType, is_composite_goal=False).order_by('pk')
            for m in qset:
                try:
                    m.recompute()
                except IntegrityError as e:
                    pass
                else:
                    complianceDict[m.compliance] += 1
                    total_goals += 1
            # recompute composite srcmegoals (AFTER individuals have been recomputed)
            qset = user.usergoals.select_related('goal').filter(goal__goalType=srcmeGoalType, is_composite_goal=True).prefetch_related('constituentGoals').order_by('pk')
            for m in qset:
                try:
                    m.recompute()
                except IntegrityError as e:
                    pass
                else:
                    complianceDict[m.compliance] += 1
                    total_goals += 1
            #
            # finally compute aggregate compliance for this user
            for level in UserGoal.COMPLIANCE_LEVELS:
                if complianceDict[level]:
                    compliance = level
                    break # agg. compliance set to highest-priority level
            else:
                # no breaks encountered
                logger.warning('Invalid complianceDict for user {0}. Could not find level.'.format(user))
                compliance = UserGoal.INCOMPLETE_PROFILE
            if compliance == UserGoal.COMPLIANT:
                # check for incomplete profile (since user may be missing some goals)
                if not profile.isCompleteForGoals():
                    compliance = UserGoal.INCOMPLETE_PROFILE
            # update orgmember.compliance cached value
            qset = user.orgmembers.filter(organization=profile.organization)
            for orgmember in qset:
                if orgmember.compliance != compliance:
                    orgmember.compliance = compliance
                    orgmember.save(update_fields=('compliance',))
                    self.stdout.write('Updated compliance of {0.user} to {0.compliance}'.format(orgmember))
