import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from users.models import User
from goals.models import UserGoal

logger = logging.getLogger('mgmt.goals')

class Command(BaseCommand):
    help = "For existing users with UserGoals, call rematchGoals to check for new goals and remove stale goals."

    def handle(self, *args, **options):
        # get distinct users
        userids = UserGoal.objects.all().values_list('user', flat=True).distinct().order_by('user')
        total = 0
        for userid in userids:
            user = User.objects.get(pk=userid)
            new_goals = UserGoal.objects.rematchGoals(user)
            for ug in new_goals:
                self.stdout.write("Created UserGoal {0}".format(ug))
            total += len(new_goals)
        msg = 'rematchGoals: num new UserGoals created: {0}'.format(total)
        logger.info(msg)
        self.stdout.write(msg)
