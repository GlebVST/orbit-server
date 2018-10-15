import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from users.auth0_tools import Auth0Api
from users.enterprise_serializers import OrgMemberFormSerializer
from users.emailutils import sendPasswordTicketEmail
from users.models import (
        User,
        Degree,
        Organization,
        OrgMember
    )
logger = logging.getLogger('mgmt.eadmin')

class Command(BaseCommand):
    help = "Create new Enterprise Admin user for the given organization, firstName, lastName, email."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('orgcode',
                help='Organization code - must already exist in the db.')
        parser.add_argument('firstname',
                help='First Name of user.')
        parser.add_argument('lastname',
                help='Last Name of user.')
        parser.add_argument('email',
                help='User email - if already exists, will raise error.')

    def handle(self, *args, **options):
        try:
            org = Organization.objects.get(code__iexact=options['orgcode'])
        except Organization.DoesNotExist:
            self.stderr.write('Invalid Organization code: does not exist')
            return
        # check email
        email = options['email']
        qset = User.objects.filter(email__iexact=email)
        if qset.exists():
            u = qset[0]
            self.stderr.write('Found existing user with email: {0.email}'.format(u))
            return
        degree = Degree.objects.get(abbrev='Other')
        api = Auth0Api()
        password_ticket = settings.ENV_TYPE == settings.ENV_PROD
        form_data = {
            'firstName': options['firstname'],
            'lastName': options['lastname'],
            'email': email,
            'degrees': [degree,],
            'password_ticket': password_ticket,
            'is_admin': True
        }
        ser = OrgMemberFormSerializer(data=form_data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            orgmember = ser.save(organization=org, apiConn=api)
            msg = u"Created Enterprise Admin: {0}".format(orgmember)
            logger.info(msg)
            self.stdout.write(msg)