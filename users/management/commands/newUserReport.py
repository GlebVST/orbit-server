import logging
from datetime import timedelta
from smtplib import SMTPException
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from users.models import Profile, SubscriptionPlan, UserSubscription
from users.emailutils import sendNewUserReportEmail
from users.auth0_tools import Auth0Api()

logger = logging.getLogger('mgmt.newuser')


def checkInactiveProfilePlans():
    """Find users who never activated a subscription and whose initial selected planId is now inactive
    Find a corresponding active plan and update their profile.planId.
    This is done so that in case the user returns to activate their subscription, they will be on
    an active plan
    Returns: list of profiles whose planId is inactive but could not be corrected
    """
    inactive_plans = SubscriptionPlan.objects.filter(active=False).order_by('pk')
    planIds = [p.planId for p in inactive_plans]
    if not planIds:
        return []
    planDict = {}
    tofix = []
    for p in inactive_plans:
        # Find an active public plan in the same group as the inactive plan
        fkwargs = dict(active=True, is_public=True, plan_key=p.plan_key, plan_type=p.plan_type)
        qs = SubscriptionPlan.objects.filter(**fkwargs).order_by('price','pk')
        if qs.exists():
            planDict[p.planId] = qs[0]
        else:
            logger.warning('checkInactivePlans: could not find a similar active plan for inactive plan: {0.pk}|{0}'.format(p))
    # Find users whose profile.planId is set to an inactive plan
    tofix = []
    profiles = Profile.objects.filter(planId__in=planIds).order_by('pk')
    for profile in profiles:
        user_subs = UserSubscription.objects.getLatestSubscription(profile.user)
        if not user_subs:
            # User never started a subscription, but their initial plan selection is now inactive.
            # Change planId to active public plan in case user decides to activate their subscription later
            old_planId = profile.planId
            active_plan = planDict.get(old_planId, None)
            if active_plan:
                profile.planId = active_plan.planId
                profile.save(update_fields=('planId',))
                logger.info('User {0.pk}|{0} has no subscription. Updated planId from inactive:{1} to active:{0.planId}.'.format(profile, old_planId))
            else:
                tofix.append(profile)
                logger.warning('User {0.pk}|{0} has no subscription. Profile.planId is inactive plan:{0.planId}.'.format(profile))
    return tofix

class Command(BaseCommand):
    help = "Finds the list of new users created in the past 24 hours and sends an email report to SALES_EMAIL"

    def handle(self, *args, **options):
        try:
            now = timezone.now()
            # inactive plans check
            profilesToFix = checkInactiveProfilePlans()
            cutoff = now - timedelta(days=1)
            profiles = Profile.objects.filter(created__gte=cutoff).order_by('created')
            if profilesToFix or profiles.count():
                sendNewUserReportEmail(profiles, profilesToFix)
            cutoff = now - timedelta(days=90)
            profiles = Profile.objects.filter(verified=False, created__gte=cutoff).order_by('created')
            if profiles.count():
                api = Auth0Api()
                num_upd = api.checkVerified(profiles) # check and update profile.verified for the given profiles
                logger.info('Num profile.verified updated: {0}'.format(num_upd))
        except SMTPException as e:
            logger.exception('New User Report Email to {0} failed'.format(email_to))
        except Exception as e:
            logger.exception('newUserReport fatal exception')
