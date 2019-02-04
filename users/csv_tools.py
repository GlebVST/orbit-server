import logging
import csv
from time import sleep
from cStringIO import StringIO
from dateutil.parser import parse as dparse
from smtplib import SMTPException
from django.core import mail
from django.conf import settings
from django.db import transaction
from common.signals import profile_saved
from users.auth0_tools import Auth0Api
from users.enterprise_serializers import (
    OrgMemberFormSerializer,
    OrgGroupSerializer,
)
from users.emailutils import sendPasswordTicketEmail
from users.models import (
    User,
    Country,
    Degree,
    PracticeSpecialty,
    State,
    Organization,
    OrgGroup,
    OrgFile,
    OrgMember,
    SubSpecialty,
    LicenseType,
    StateLicense,
    SubscriptionPlan,
)
logger = logging.getLogger('mgmt.csv')

class CsvDialect(csv.Dialect):
    """Describe the usual properties of Excel-generated CSV files."""
    delimiter = ';'
    quotechar = '"'
    doublequote = True
    skipinitialspace = False
    lineterminator = '\r\n'
    quoting = csv.QUOTE_MINIMAL
csv.register_dialect("csv", CsvDialect)

class CsvImport():

    def __init__(self, multi_value_delimiter = ',', stdout = None):
        self.multi_value_delimiter = multi_value_delimiter
        self.stdout = stdout

    def parseMultiDictField(self, model, fieldName, dataDict, index = 0):
        """Parse fieldName from the given row and return list of values
        Args:
        Returns: list. Empty list is valid.
        Raise ValueError if transformed value not found in dataDict
        """
        output = []
        if self.multi_value_delimiter in model[fieldName]:
            values = model[fieldName].split(self.multi_value_delimiter)
        else:
            values = [model[fieldName], ]
        for v in values:
            tv = v.strip().upper() # transform value before compare to dataDict
            if not tv: # can be empty, move on
                continue
            if tv not in dataDict:
                error_msg = "Invalid {0} at row {1}: {2}".format(fieldName, index, v)
                raise ValueError(error_msg)
            output.append(dataDict[tv])
        return output

    def parseMultiDateField(self, model, fieldName, index = 0):
        """Parse fieldName from the given row and return list of dates
        Args:
        Returns: list. Empty list is valid.
        Raise ValueError if failed to construct dates
        """
        output = []
        if self.multi_value_delimiter in model[fieldName]:
            values = model[fieldName].split(self.multi_value_delimiter)
        else:
            values = [model[fieldName], ]
        for v in values:
            tv = v.strip().upper() # clear value before converting to date
            if not tv: # can be empty, move on
                continue
            try: 
                output.append(dparse(tv))
            except ValueError, e:
                error_msg = "Invalid {0}: {1}".format(fieldName, v)
                raise ValueError(error_msg)
        return output
    
    def print_out(self, msg, is_error = False):
        if self.stdout:
            self.stdout.write(msg + '\n')
        if is_error:
            logger.warning(msg)
        else:
            logger.info(msg)

            
class ProviderCsvImport(CsvImport):
    FIELD_NAMES = (
        ('First Name', 'FirstName'),
        ('Last Name', 'LastName'),
        ('NPI Number', 'NPINumber'),
        ("Birthdate (MM/DD/YY)", 'Birthdate'),
        ('Email', 'Email'),
        ('Practice Divistion', 'Group'),
        ("Degree", "Role"),
        ("Residency Training Program", 'ResidencyTraining'),
        ("Residency Graduation Date", 'ResidencyTrainingDate'),
        ("State Licenses", 'States'),
        ("State License Expiry Dates", 'StateLicenseExpiryDates'),
        ("DEA Certificate States", 'DEAStates'),
        ("DEA Certificate Expiry Dates", 'DEAExpiry'),
        ("ABMS Active Board Certifications", 'ActiveCoarcCertifications'),
        ("Specialty", 'Specialty'),
        ("Subspecialty scope of practice", 'SubSpecialty'),
    )
    RAW_FIELD_NAMES = [t[0] for t in FIELD_NAMES]
    FIELD_NAME_MAP = {t[0]:t[1] for t in FIELD_NAMES}

    def throwValueError(self, row, fieldName, value):
        error_msg = "Invalid {0} at row {1}: {2}".format(fieldName, row, value)
        raise ValueError(error_msg)
    
    def processOrgFile(self, org_id, src_file, dry_run = False, test_ticket = False):
        num_existing = 0
        created = [] # list of OrgMembers
        try:
            org = Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            error_msg = "Missing organisation ID: {0}".format(org_id)
            self.print_out(error_msg, True)
            return False
        try:
            plan = SubscriptionPlan.objects.getEnterprisePlanForOrg(org)
        except IndexError:
            error_msg = "Failed to find SubscriptionPlan for Organization: {0.name}".format(org)
            self.print_out(error_msg, True)
            return False

        country_usa = Country.objects.get(code=Country.USA)

        # build lookup dicts
        qset = Degree.objects.all()
        degreeDict = {m.abbrev:m for m in qset}
        qset = PracticeSpecialty.objects.all()
        psDict = {m.name.upper():m for m in qset}
        qset = SubSpecialty.objects.all()
        subSpecDict = {m.name.upper():m for m in qset}
        qset = State.objects.all()
        stateDict = {m.abbrev:m for m in qset}
        qset = User.objects.all()
        usersDict = {u.email:u for u in qset}
        qset = OrgGroup.objects.filter(organization = org)
        groupsDict = {g.name:g for g in qset}
        qset = LicenseType.objects.all()
        licenseTypesDict = {g.name:g for g in qset}

        try:
            f = StringIO(src_file.read())
            reader = csv.DictReader(f, fieldnames=self.RAW_FIELD_NAMES, restkey='extra', dialect='csv')
            all_data = [row for row in reader]
            raw_data = all_data[1:]
            # pre-process 1: map to fieldnames and remove template data
            data = []
            for d in raw_data:
                if d['First Name'].strip() == '':
                    continue
                dd = {self.FIELD_NAME_MAP[key]:d[key] for key in d}
                data.append(dd)
            # pre-process 2: check valid FKs
            pos = 1
            for d in data:
                # map degree
                role = d['Role'].strip().upper()
                if role not in degreeDict:
                    self.throwValueError('Degree', pos, role)
                d['degree'] = degreeDict[role]

                # birthdate (optional)
                if d['Birthdate']:
                    try:
                        d['Birthdate'] = dparse(d['Birthdate'])
                    except ValueError, e:
                        self.throwValueError('Birthdate', pos, d['Birthdate'])

                # Multi-value fields
                d['specialties'] = self.parseMultiDictField(d, 'Specialty', psDict, pos) # 0+ PracticeSpecialty instances
                d['subspecialties'] = self.parseMultiDictField(d, 'SubSpecialty', subSpecDict, pos) # 0+ SubSpecialty instances
                d['states'] = self.parseMultiDictField(d, 'States', stateDict, pos) # 0+ State instances
                d['stateExpiryDates'] = self.parseMultiDateField(d, 'StateLicenseExpiryDates', pos) # 0+ Date instances
                d['deaStates'] = self.parseMultiDictField(d, 'DEAStates', stateDict, pos) # 0+ State instances
                d['deaExpiryDates'] = self.parseMultiDateField(d, 'DEAExpiry', pos) # 0+ Date instances
                pos += 1
            # filter out existing users
            fdata = []
            num_new = 0
            for d in data:
                email = d['Email']
                # check if email already exists
                if email in usersDict:
                    self.print_out('User account already exists for email {0}'.format(email))
                    num_existing += 1
                else:
                    if dry_run:
                        self.print_out('[dry run] create new account for: {0}'.format(email))
                    fdata.append(d)
                    num_new += 1
            if dry_run:
                self.print_out('Num existing users: {0}'.format(num_existing))
                self.print_out('Num new users: {0}'.format(num_new))
                self.print_out('Dry run over.')
                return
            if not fdata:
                self.print_out('Num existing users: {0}'.format(num_existing))
                self.print_out('No new users found.')

            auth0 = Auth0Api()
            for d in fdata:
                # prepare form data for serializer
                groupName = d['Group'].strip()
                group = None
                if not groupName in groupsDict:
                    groupSer = OrgGroupSerializer(data={
                        'name': groupName
                    })
                    if groupSer.is_valid():
                        group = groupSer.save(organization=org)
                        groupsDict.update({group.name:group})
                else:
                    group = groupsDict[groupName]

                degrees = [d['degree'].id,]
                form_data = {
                    'firstName': d['FirstName'],
                    'lastName': d['LastName'],
                    'email': d['Email'],
                    'degrees': degrees,
                    'password_ticket': False,
                    'group': group.id
                }
                ser = OrgMemberFormSerializer(data=form_data)
                ser.is_valid(raise_exception=True)
                with transaction.atomic():
                    orgmember = ser.save(organization=org, apiConn=auth0, plan=plan)
                    created.append(orgmember)
                    # Update profile
                    user = orgmember.user
                    profile = user.profile
                    if d['NPINumber']:
                        profile.npiNumber = d['NPINumber']
                    if d['Birthdate']:
                        profile.birthDate = d['Birthdate']
                    profile.country = country_usa
                    profile.save()
                    for state in d['states']:
                        profile.states.add(state)
                    for state in d['deaStates']:
                        profile.deaStates.add(state)
                    for ps in d['specialties']:
                        profile.specialties.add(ps)
                    for ps in d['subspecialties']:
                        profile.subspecialties.add(ps)
                    # ProfileCmetags
                    profile.addOrActivateCmeTags()

                    # emit profile_saved signal
                    profile_saved.send(sender=profile.__class__, user_id=user.pk)
                    msg = u"Created User/Profile records: {FirstName} {LastName}, {Email}".format(**d)
                    self.print_out(msg)

                    num_state_licenses = 0
                    for index, state in d['states']:
                        expiryDate = None
                        dates = d['stateExpiryDates']
                        if index < len(dates):
                            expiryDate = dates[index]

                        StateLicense.objects.create(
                            user=user,
                            state=state,
                            licenseType=licenseTypesDict[LicenseType.TYPE_MB],
                            expireDate=expiryDate
                        )
                        num_state_licenses += 1
                    self.print_out("Imported {} licenses for user {}".format(num_state_licenses, d['Email']))

                    num_dea_licenses = 0
                    for index, state in d['deaStates']:
                        expiryDate = None
                        dates = d['deaExpiryDates']
                        if index < len(dates):
                            expiryDate = dates[index]

                        StateLicense.objects.create(
                            user=user,
                            state=state,
                            licenseType=licenseTypesDict[LicenseType.TYPE_DEA],
                            expireDate=expiryDate
                        )
                        num_dea_licenses += 1
                    self.print_out("Imported {} DEA licenses for user {}".format(num_state_licenses, d['Email']))

            if settings.ENV_TYPE == settings.ENV_PROD or test_ticket:
                self.sendPasswordTicketEmails(org, auth0)

            # final reporting
            self.print_out('Num existing users: {0}'.format(num_existing))
            self.print_out('Num new users: {0}'.format(num_new))
            self.print_out('Num users created: {0}'.format(len(created)))
            return True
        except SMTPException, e:
            error_msg = "SMTPException: {0}".format(e)
            self.print_out(error_msg, True)
            return False
        except csv.Error, e:
            error_msg = "CsvError: {0}".format(e)
            self.print_out(error_msg, True)
            return False
        except ValueError, e:
            error_msg = "ValueError: {0}".format(e)
            self.print_out(error_msg, True)
            return False

    def sendPasswordTicketEmails(self, org, auth0):
        # Send password ticket emails for all members of the organisations who
        # don't have a `setPasswordEmailSent` flag set yet
        redirect_url = 'https://{0}{1}'.format(settings.SERVER_HOSTNAME, settings.UI_LINK_LOGIN)
        user_tickets = []
        qset = OrgMember.objects.filter(organization=org, setPasswordEmailSent=False).order_by('id')
        # generate change-password-tickets with auth0
        for orgmember in qset:
            user = orgmember.user
            profile = user.profile
            ticket_url = auth0.change_password_ticket(profile.socialId, redirect_url)
            user_tickets.append((orgmember, ticket_url))
        num_tickets = len(user_tickets)
        tickets_msg = 'Generating {0} Auth0 password-ticket emails...please wait.'.format(num_tickets)
        self.print_out(tickets_msg)

        # send out emails
        connection = mail.get_connection()
        connection.open()
        for orgmember, ticket_url in user_tickets:
            user = orgmember.user
            sending_msg = u"Sending password-ticket email for User: {0}...".format(user)
            self.print_out(sending_msg)
            msg = sendPasswordTicketEmail(orgmember, ticket_url, send_message=False)
            # send email and update flag if success
            num_sent = connection.send_messages([msg,])
            if num_sent == 1:
                orgmember.setPasswordEmailSent = True
                orgmember.save(update_fields=('setPasswordEmailSent',))
            else:
                error_msg = 'Send password-ticket email failed for {0.user}'.format(orgmember)
                self.print_out(error_msg, True)
            # small delay as we are not spammers
            sleep(0.3)

        connection.close()