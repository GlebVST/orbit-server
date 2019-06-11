import logging
import csv
from time import sleep
from cStringIO import StringIO
from dateutil.parser import parse as dparse
from smtplib import SMTPException
from django.core import mail
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from common.signals import profile_saved
from users.auth0_tools import Auth0Api
from users.enterprise_serializers import OrgMemberFormSerializer
from users.emailutils import getHostname, sendPasswordTicketEmail
from users.models import (
        User,
        SubscriptionPlan,
        Country,
        Degree,
        PracticeSpecialty,
        State,
        Organization,
        OrgGroup,
        OrgMember
    )
from pprint import pprint

logger = logging.getLogger('mgmt.import')
DELIMITER = ','

class Command(BaseCommand):
    help = "Process csv file containing user info. It creates new User accounts for any new emails found and skips over existing ones. If any error is encountered, it exits immediately."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('filename',
                help='Filename to process')
        parser.add_argument(
            '--dry_run',
            action='store_true',
            dest='dry_run',
            default=False,
            help='Dry run. Does not create any new members. Just print to console for debugging.'
        )
        parser.add_argument(
            '--test_ticket',
            action='store_true',
            dest='test_ticket',
            default=False,
            help='Applicable on test server only: send out change-password-ticket emails. This is always done in prod.'
        )

    def parseMultiValueField(self, row, fieldName, dataDict):
        """Parse fieldName from the given row and return list of values
        Args:
        Returns: list. Empty list is valid.
        Raise ValueError if transformed value not found in dataDict
        """
        output = []
        if DELIMITER in row[fieldName]:
            values = row[fieldName].split(DELIMITER)
        else:
            values = [row[fieldName],]
        for v in values:
            tv = v.strip().upper() # transform value before compare to dataDict
            if not tv: # can be empty, move on
                continue
            if tv not in dataDict:
                error_msg = "Invalid {0}: {1}".format(fieldName, v)
                raise ValueError(error_msg)
            output.append(dataDict[tv])
        return output

    def handle(self, *args, **options):
        filename = options['filename']
        fieldnames = ('First Name', 'Last Name', 'Email Address', 'Primary Role', 'Country', 'Scope of Practice', 'Residency Training', 'Graduation Date')
        num_existing = 0
        created = [] # list of OrgMembers
        country_usa = Country.objects.get(code=Country.USA)
        org = Organization.objects.get(joinCode='cpr')
        plan = SubscriptionPlan.objects.get(organization=org)
        self.stdout.write('Organization: {0.name} with plan: {1}.'.format(org, plan))
        # build lookup dicts
        qset = OrgGroup.objects.filter(organization=org)
        orgGroupDict = {m.name:m for m in qset}
        qset = Degree.objects.all()
        degreeDict = {m.abbrev:m for m in qset}
        qset = PracticeSpecialty.objects.all()
        psDict = {m.name.upper():m for m in qset}
        #qset = SubSpecialty.objects.all()
        #subSpecDict = {m.name.upper():m for m in qset}
        #qset = State.objects.all()
        #stateDict = {m.abbrev:m for m in qset}
        try:
            f = open(filename, 'rb')
            reader = csv.DictReader(f, fieldnames=fieldnames, restkey='extra')
            all_data = [row for row in reader]
            data = all_data[1:]
            # pre-process: check valid FKs
            for d in data:
                email = d['Email Address']
                if settings.ENV_TYPE != settings.ENV_PROD:
                    d['email'] = email.replace('@', '.') + '@orbitcme.com'
                else:
                    d['email'] = email
                d['degree'] = degreeDict['Other']
                specialty = d['Scope of Practice'].upper()
                d['specialties'] = [psDict[specialty],]
                # residencyEndDate
                if d['Graduation Date']:
                    d['residencyEndDate'] = dparse(d['Graduation Date'])
                else:
                    d['residencyEndDate'] = None
            # filter out existing users
            fdata = []
            num_new = 0
            for d in data:
                # check if email already exists
                email = d['email']
                qset = User.objects.filter(email__iexact=email)
                if qset.exists():
                    self.stdout.write('User account already exists for email {0}'.format(email))
                    num_existing += 1
                else:
                    if options['dry_run']:
                        self.stdout.write('[dry run] create new account for: {0}'.format(email))
                    fdata.append(d)
                    num_new += 1
            if options['dry_run']:
                self.stdout.write('Num existing users: {0}'.format(num_existing))
                self.stdout.write('Num new users: {0}'.format(num_new))
                self.stdout.write('Dry run over.')
                return
            if not fdata:
                self.stdout.write('Num existing users: {0}'.format(num_existing))
                self.stdout.write('No new users found.')
                return
            api = Auth0Api()
            for d in fdata:
                # prepare form data for serializer
                degrees = [d['degree'].pk,]
                form_data = {
                    'firstName': d['First Name'],
                    'lastName': d['Last Name'],
                    'email': d['email'],
                    'password_ticket': False,
                    'country': country_usa.pk,
                    'degrees': degrees,
                    'specialties': [],
                    'subspecialties': [],
                    'states': [],
                    'deaStates': [],
                    'hospitals': [],
                    'residency_program': None,
                }
                if d['residencyEndDate']:
                    yr = str(d['residencyEndDate'].year)
                    form_data['group'] = orgGroupDict[yr].pk
                else:
                    form_data['group'] = orgGroupDict['1899'].pk
                ser = OrgMemberFormSerializer(data=form_data)
                ser.is_valid(raise_exception=True)
                with transaction.atomic():
                    orgmember = ser.save(organization=org, plan=plan, apiConn=api)
                    created.append(orgmember)
                    # Update profile
                    user = orgmember.user
                    profile = user.profile
                    if d['residencyEndDate']:
                        profile.residencyEndDate = d['residencyEndDate']
                    profile.save()
                    for ps in d['specialties']:
                        profile.specialties.add(ps)
                    #for ps in d['subspecialties']:
                    #    profile.subspecialties.add(ps)
                    #for state in d['states']:
                    #    profile.states.add(state)
                    # ProfileCmetags
                    add_tags = profile.addOrActivateCmeTags()
                    # emit profile_saved signal
                    #ret = profile_saved.send(sender=profile.__class__, user_id=user.pk)
                msg = u"Created OrgMember: {0.pk}|{0}".format(orgmember)
                logger.info(msg)
                self.stdout.write(msg)
            # change-password-tickets
            if settings.ENV_TYPE == settings.ENV_PROD or options['test_ticket']:
                redirect_url = 'https://{0}{1}'.format(getHostname(), settings.UI_LINK_LOGIN)
                user_tickets = []
                qset = OrgMember.objects.filter(organization=org, setPasswordEmailSent=False).order_by('id')
                for orgmember in qset:
                    user = orgmember.user
                    profile = user.profile
                    ticket_url = apiConn.change_password_ticket(profile.socialId, redirect_url)
                    user_tickets.append((orgmember, ticket_url))
                # send out emails
                connection = mail.get_connection()
                connection.open()
                num_tickets = len(user_tickets)
                self.stdout.write('Generating {0} Auth0 password-ticket emails with redirect_url: {1}'.format(num_tickets, redirect_url))
                # send email and update flag
                for orgmember, ticket_url in user_tickets:
                    user = orgmember.user
                    profile = user.profile
                    self.stdout.write(u"Processing User: {0}...".format(user))
                    msg = sendPasswordTicketEmail(orgmember, ticket_url, send_message=False)
                    num_sent = connection.send([msg,])
                    if num_sent == 1:
                        orgmember.setPasswordEmailSent = True
                        orgmember.save(update_fields=('setPasswordEmailSent',))
                    else:
                        error_msg = ' ! send password-ticket email failed for {0.user}'.format(orgmember)
                        logger.warning(error_msg)
                        self.stdout.write(error_msg)
                    sleep(0.5)
                connection.close()
            # final reporting
            self.stdout.write('Num existing users: {0}'.format(num_existing))
            self.stdout.write('Num new users: {0}'.format(num_new))
        except SMTPException as e:
            error_msg = "SMTPException: {0}".format(e)
            logger.warning(error_msg)
            self.stderr.write(error_msg)
            return
        except csv.Error as e:
            error_msg = "CsvError: {0}".format(e)
            logger.warning(error_msg)
            self.stderr.write(error_msg)
            return
        except ValueError as e:
            error_msg = "ValueError: {0}".format(e)
            logger.warning(error_msg)
            self.stderr.write(error_msg)
            return
        else:
            if not options['dry_run']:
                self.stdout.write('import users completed')
