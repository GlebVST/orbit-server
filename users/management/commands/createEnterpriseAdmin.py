import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from users.auth0_tools import Auth0Api
from users.enterprise_serializers import OrgMemberFormSerializer
from users.emailutils import sendPasswordTicketEmail
from users.models import (
        User,
        Country,
        Degree,
        Organization,
        OrgMember,
        SubscriptionPlan,
        OrgAgg
    )
logger = logging.getLogger('mgmt.eadmin')

class Command(BaseCommand):
    help = "Create new Enterprise Admin user for the given organization, planId, firstName, lastName, email."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('orgcode',
                help='Organization joincode. One word (no whitespace). Must already exist in the db.')
        parser.add_argument('planId',
                help='Enterprise SubscriptionPlan.planId (no whitespace). Must already exist in the db.')
        parser.add_argument('firstname',
                help='First Name of user.')
        parser.add_argument('lastname',
                help='Last Name of user.')
        parser.add_argument('email',
                help='User email - if already exists, will raise error.')

    def handle(self, *args, **options):
        try:
            org = Organization.objects.get(joinCode=options['orgcode'])
        except Organization.DoesNotExist:
            self.stderr.write('Invalid Organization joinCode: does not exist')
            return
        try:
            plan = SubscriptionPlan.objects.get(planId=options['planId'])
        except SubscriptionPlan.DoesNotExist:
            self.stderr.write('Invalid SubscriptionPlan planId: please check SubscriptionPlan.planId field for valid values.')
            return
        else:
            # validation check: plan.org must match provided org
            if plan.organization != org:
                self.stderr.write('Validation Error: Provided org {0.name} does not match the org assigned to planId: {1.organization}'.format(org, plan))
                return

        # check email
        email = options['email']
        qset = User.objects.filter(email__iexact=email)
        if qset.exists():
            u = qset[0]
            self.stderr.write('Found existing user with email: {0.email}'.format(u))
            return
        country_usa = Country.objects.get(code=Country.USA)
        degree = Degree.objects.get(abbrev='Other')
        api = Auth0Api()
        do_password_ticket = settings.ENV_TYPE == settings.ENV_PROD
        form_data = {
            'is_admin': True,
            'group': None,
            'password_ticket': do_password_ticket,
            'firstName': options['firstname'],
            'lastName': options['lastname'],
            'email': email,
            'country': country_usa.pk,
            'degrees': [degree.pk,],
            'specialties': [],
            'subspecialties': [],
            'states': [],
            'deaStates': [],
            'fluoroscopyStates': [],
            'hospitals': [],
            'residency_program': None,
            'npiNumber': ''
        }
        ser = OrgMemberFormSerializer(data=form_data)
        ser.is_valid(raise_exception=True)
        try:
            orgmember = ser.save(organization=org, apiConn=api, plan=plan)
            profile = orgmember.user.profile
            msg = "Created Enterprise Admin: {0} on plan: {1}. User Auth0 Id:{2.socialId}".format(orgmember, plan, profile)
            logger.info(msg)
            self.stdout.write(msg)
            # initialize stats used by UI
            org.computeCreditsEarned()
            org.computeProviderStats()
            # store first OrgAgg entry (TeamStats view expects at least one entry)
            oa = OrgAgg.objects.compute_user_stats(org)
            logger.info('Initialized first OrgAgg entry for TeamStats: {0}'.format(oa))
        except Exception as e:
            msg = "createEnterpriseAdmin exception: {0}".format(e)
            self.stdout.write(msg)
            logger.exception(msg)
