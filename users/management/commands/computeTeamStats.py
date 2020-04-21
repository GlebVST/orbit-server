import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from users.models import Organization, OrgMember, OrgAgg

logger = logging.getLogger('mgmt.orgstat')

class Command(BaseCommand):
    help = "Compute and update stats for active enterprise orgs. This should be called by a daily cron task."

    def handle(self, *args, **options):
        # get distinct orgs having members and computeTeamStats flag set to true
        orgids = OrgMember.objects \
            .select_related('org') \
            .filter(org__computeTeamStats=True) \
            .values_list('organization', flat=True) \
            .distinct()
        for orgid in orgids:
            org = Organization.objects.get(pk=orgid)
            org.computeCreditsEarned()
            # provider stat: current vs end-of-prior-month
            org.computeProviderStats()
            # update OrgAgg user stats
            orgAgg = OrgAgg.objects.compute_user_stats(org)
            logger.info('Saved OrgAgg {0.pk} {0.day}'.format(orgAgg))
