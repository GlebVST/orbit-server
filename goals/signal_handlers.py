import logging
from django.contrib.auth.models import User
from django.dispatch import receiver
from common.signals import profile_saved
from .models import UserGoal

logger = logging.getLogger('gen.sigs')

def handleProfileSaved(sender, **kwargs):
    user_id = kwargs['user_id']
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error('handleProfileSaved: invalid user_id: {0}'.format(user_id))
    else:
        if user.profile.allowUserGoals():
            # check if user is an active non-admin orgmember
            qs = user.orgmembers.filter(is_admin=False, removeDate__isnull=True)
            if not qs.exists():
                return
            usergoals = UserGoal.objects.rematchGoals(user)
            if usergoals:
                logger.info('handleProfileSaved: {0} new usergoals created.'.format(len(usergoals)))

#handler bound to signal once for each unique dispatch_uid value
profile_saved.connect(handleProfileSaved, dispatch_uid='handle-profile-saved')
