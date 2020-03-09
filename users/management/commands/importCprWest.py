import logging
import csv
from fuzzywuzzy import fuzz, process
from datetime import datetime
import pytz
from time import sleep
from dateutil.parser import parse as dparse
from smtplib import SMTPException
from django.core import mail
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from common.signals import profile_saved
from users.auth0_tools import Auth0Api
from users.enterprise_serializers import OrgMemberFormSerializer
#from users.emailutils import getHostname, sendPasswordTicketEmail
from users.models import (
        User,
        SubscriptionPlan,
        Country,
        Degree,
        PracticeSpecialty,
        State,
        Organization,
        OrgGroup,
        OrgMember,
        ResidencyProgram
    )
from pprint import pprint

logger = logging.getLogger('mgmt.import')
DELIMITER = ','

def assignRPNames(names):
    qs = ResidencyProgram.objects.all().order_by('name')
    dbnames = [m.name for m in qs]
    assigned = {}
    for name in names:
        #print('Finding match for {0}'.format(name))
        ret = process.extractOne(name, dbnames, scorer=fuzz.token_set_ratio)
        #print(ret)
        matchName = ret[0]; score = ret[1]
        if score > 75:
            assigned[name] = matchName
        else:
            msg = '! No match found for {0}'.format(name)
            print(msg)
            logger.warning(msg)
    return assigned


class Command(BaseCommand):
    help = "Process csv file containing cpr user info. It creates new User accounts for any new emails found and skips over existing ones. If any error is encountered, it exits immediately."

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
        fieldnames = ('Group', 'First Name', 'Last Name', 'Residency Program', 'Residency Graduation Year', 'Email Address')
        num_existing = 0
        created = [] # list of OrgMembers
        deg_md = Degree.objects.get(abbrev='MD')
        ps_rad = PracticeSpecialty.objects.get(name='Radiology')
        country_usa = Country.objects.get(code=Country.USA)
        org = Organization.objects.get(joinCode='cpr')
        plan = SubscriptionPlan.objects.getEnterprisePlanForOrg(org)
        self.stdout.write('Organization: {0.name} with plan: {1}.'.format(org, plan))
        # build lookup dicts
        qset = OrgGroup.objects.filter(organization=org)
        orgGroupDict = {m.name:m for m in qset}
        qset = ResidencyProgram.objects.all()
        rpDict = {m.name:m for m in qset}

        rpnames = set([]) # from file
        try:
            f = open(filename, 'r')
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
                rpname = d['Residency Program']
                rpnames.add(rpname)
                # residencyEndDate
                if d['Residency Graduation Year']:
                    try:
                        yr = int(d['Residency Graduation Year'])
                    except ValueError:
                        pass
                    else:
                        d['residencyEndDate'] = datetime(yr, 7,1, tzinfo=pytz.utc)
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
                        self.stdout.write('[dry run] create new account for: {0} in Group {1}'.format(email, d['Group']))
                    fdata.append(d)
                    num_new += 1
            rpAssign = assignRPNames(rpnames)
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
                form_data = {
                    'is_admin': False,    
                    'firstName': d['First Name'],
                    'lastName': d['Last Name'],
                    'email': d['email'],
                    'password_ticket': False,
                    'group': orgGroupDict[d['Group']].pk,
                    'country': country_usa.pk,
                    'degrees': [deg_md.pk,],
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
                with transaction.atomic():
                    orgmember = ser.save(organization=org, plan=plan, apiConn=api)
                    created.append(orgmember)
                    # Update profile
                    user = orgmember.user
                    profile = user.profile
                    # this is NOT done by OrgMemberFormSerializer! - it takes in the args but does not use them
                    profile.degrees.add(deg_md)
                    profile.specialties.add(ps_rad)
                    # residency
                    rpname = d['Residency Program']; rp = None
                    if rpname in rpAssign:
                        rp = rpDict[rpAssign[rpname]] 
                        profile.residency_program = rp
                        profile.save(update_fields=('residency_program',))
                    if d['residencyEndDate']:
                        profile.residencyEndDate = d['residencyEndDate']
                        profile.save(update_fields=('residencyEndDate',))
                    # ProfileCmetags
                    add_tags = profile.addOrActivateCmeTags()
                    # emit profile_saved signal
                    ret = profile_saved.send(sender=profile.__class__, user_id=user.pk)
                msg = u"Created OrgMember: {0.pk}|{0} rp:{1.residency_program} date:{1.residencyEndDate}".format(orgmember, profile)
                logger.info(msg)
                self.stdout.write(msg)
                sleep(0.5)
            # final reporting
            self.stdout.write('Num existing users: {0}'.format(num_existing))
            self.stdout.write('Num new users: {0}'.format(num_new))
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
