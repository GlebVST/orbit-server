import logging
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from users.models import User, Profile
from goals.models import GoalType, UserGoal

logger = logging.getLogger('mgmt.goals')
CUTOFF = 30

class Command(BaseCommand):
    help = "Recompute all UserGoals to update their status."

    def handle(self, *args, **options):
        licenseGoalType = GoalType.objects.get(name=GoalType.LICENSE)
        cmeGoalType = GoalType.objects.get(name=GoalType.CME)
        # get distinct users
        users = UserGoal.objects.all().values_list('user', flat=True).distinct().order_by('user')
        now = timezone.now()
        for userid in users:
            user = User.objects.get(pk=userid)
            self.stdout.write('Process user {0}'.format(user))
            profile = Profile.objects.filter(user=userid).prefetch_related('specialties')[0]
            numProfileSpecs = profile.specialties.count()
            userLicenseDict = dict()
            total_goals = 0
            statusDict = {
                    UserGoal.PASTDUE: 0,
                    UserGoal.IN_PROGRESS: 0,
                    UserGoal.COMPLETED: 0
            }
            # recompute user license goals.
            qset = user.usergoals.select_related('goal','license').filter(goal__goalType=licenseGoalType)
            for m in qset:
                userLicenseDict[m.goal.pk] = m.license
                old_status = m.status
                m.recompute()
                statusDict[m.status] += 1
                total_goals += 1
                if m.status != old_status:
                    self.stdout.write('Updated status of {0} to {0.status}'.format(m))
            # recompute user cmegoals
            qset = user.usergoals.select_related('goal').filter(goal__goalType=cmeGoalType).prefetch_related('cmeGoals').order_by('pk')
            for m in qset:
                old_status = m.status
                m.recompute(userLicenseDict, numProfileSpecs)
                statusDict[m.status] += 1
                total_goals += 1
                if m.status != old_status:
                    self.stdout.write('Updated status of {0} to {0.status}'.format(m))
            # compute compliance
            # if any are pastdue, compliance = PASTDUE
            if statusDict[UserGoal.PASTDUE]:
                compliance = UserGoal.PASTDUE
            # if all are completed, compliance = COMPLETED
            elif statusDict[UserGoal.COMPLETED] == total_goals:
                compliance = UserGoal.COMPLETED
            else:
                compliance = UserGoal.IN_PROGRESS
            # update orgmember.compliance cached value
            qset = user.orgmembers.all()
            for orgmember in qset:
                if orgmember.compliance != compliance:
                    orgmember.compliance = compliance
                    orgmember.save(update_fields=('compliance',))
                    self.stdout.write('Updated compliance of {0.user} to {0.compliance}'.format(orgmember))
