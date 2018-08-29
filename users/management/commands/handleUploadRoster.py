import logging
import csv
from time import sleep
from cStringIO import StringIO
from smtplib import SMTPException
from django.core import mail
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from common.signals import profile_saved
from users.auth0_tools import Auth0Api
from users.enterprise_serializers import OrgMemberFormSerializer
from users.emailutils import sendPasswordTicketEmail
from users.models import (
        User,
        Country,
        Degree,
        PracticeSpecialty,
        State,
        OrgFile,
        OrgMember
    )
from pprint import pprint

logger = logging.getLogger('mgmt.orgfile')
DELIMITER = ','

class Command(BaseCommand):
    help = "Process Uploaded Roster file for the given file_id. It creates new User accounts for any new emails found and skips over existing ones. If any error is encountered, it exits immediately."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('file_id', type=int,
                help='File ID of the uploaded roster file to process')
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
        file_id = options['file_id']
        fieldnames = ('LastName', 'FirstName', 'Email', 'Role', 'Specialty', 'SubSpecialty', 'State')
        num_existing = 0
        created = [] # list of OrgMembers
        country_usa = Country.objects.get(name=Country.USA)
        # build lookup dicts
        qset = Degree.objects.all()
        degreeDict = {m.abbrev:m for m in qset}
        qset = PracticeSpecialty.objects.all()
        psDict = {m.name.upper():m for m in qset}
        qset = SubSpecialty.objects.all()
        subSpecDict = {m.name.upper():m for m in qset}
        qset = State.objects.all()
        stateDict = {m.abbrev:m for m in qset}
        try:
            orgfile = OrgFile.objects.get(pk=file_id)
            org = orgfile.organization
            self.stdout.write('Pre-process roster file for {0.code}: checking validity...'.format(org))
            srcfile = orgfile.csvfile if orgfile.csvfile else orgfile.document
            f = StringIO(srcfile.read())
            reader = csv.DictReader(f, fieldnames=fieldnames, restkey='extra')
            all_data = [row for row in reader]
            data = all_data[1:]
            # pre-process: check valid FKs
            for d in data:
                role = d['Role'].strip().upper()
                if role not in degreeDict:
                    error_msg = "Invalid Primary Role: {0}".format(role)
                    logger.warning(error_msg)
                    self.stdout.write(error_msg)
                    return
                d['degree'] = degreeDict[role]
                # Multi-value fields
                d['specialties'] = self.parseMultiValueField(d, 'Specialty', psDict) # 0+ PracticeSpecialty instances
                d['subspecialties'] = self.parseMultiValueField(d, 'SubSpecialty', subSpecDict) # 0+ SubSpecialty instances
                d['states'] = self.parseMultiValueField(d, 'State', stateDict) # 0+ State instances
            # filter out existing users
            fdata = []
            num_new = 0
            for d in data:
                email = d['Email']
                # check if email already exists
                qset = User.objects.filter(email=email)
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
                degrees = [d['degree'],]
                form_data = {
                    'firstName': d['FirstName'],
                    'lastName': d['LastName'],
                    'email': email,
                    'degrees': degrees,
                    'password_ticket': False
                }
                ser = OrgMemberFormSerializer(data=form_data)
                ser.is_valid(raise_exception=True)
                with transaction.atomic():
                    orgmember = ser.save(organization=org, apiConn=api)
                    created.append(orgmember)
                    # Update profile
                    user = orgmember.user
                    profile = user.profile
                    profile.country = country_usa
                    for state in d['states']:
                        profile.states.add(state)
                    for ps in d['specialties']:
                        profile.specialties.add(ps)
                    for ps in d['subspecialties']:
                        profile.subspecialties.add(ps)
                    # ProfileCmetags
                    add_tags = profile.addOrActivateCmeTags()
                    # emit profile_saved signal
                    ret = profile_saved.send(
                            sender=profile.__class__, user_id=user.pk)
                msg = u"Created User: {FirstName} {LastName}, {Role}".format(**d)
                logger.info(msg)
            # change-password-tickets
            if settings.ENV_TYPE == settings.ENV_PROD or options['test_ticket']:
                redirect_url = 'https://{0}{1}'.format(settings.SERVER_HOSTNAME, settings.UI_LINK_LOGIN)
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
                self.stdout.write('Generating {0} Auth0 password-ticket emails...please wait.'.format(num_tickets))
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
                        error_msg = ' - send password-ticket email failed'.format(orgmember))
                        logger.warning(error_msg)
                        self.stdout.write(error_msg)
                    sleep(0.3)
                connection.close()
            # final reporting
            self.stdout.write('Num existing users: {0}'.format(num_existing))
            self.stdout.write('Num new users: {0}'.format(num_new))
        except OrgFile.DoesNotExist:
            error_msg = "Invalid file_id: {0}".format(file_id)
            self.stderr.write(error_msg)
            return
        except SMTPException, e:
            error_msg = "SMTPException: {0}".format(e)
            logger.warning(error_msg)
            self.stderr.write(error_msg)
            return
        except csv.Error, e:
            error_msg = "CsvError: {0}".format(e)
            logger.warning(error_msg)
            self.stderr.write(error_msg)
            return
        except ValueError, e:
            error_msg = "ValueError: {0}".format(e)
            logger.warning(error_msg)
            self.stderr.write(error_msg)
            return
        else:
            if not options['dry_run']:
                orgfile.processed = True
                orgfile.save(update_fields=('processed',))
