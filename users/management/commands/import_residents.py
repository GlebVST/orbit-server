from __future__ import unicode_literals
from django.core.management.base import BaseCommand, CommandError
import logging
import csv
from time import sleep
from io import StringIO
from dateutil.parser import parse as dparse
from django.db import transaction
from hashids import Hashids

from users.models import Profile, Degree, Country, ResidencyProgram
from users.models.residents import Case

logger = logging.getLogger('mgmt.csv')

class CsvDialect(csv.Dialect):
    """Describe the usual properties of Excel-generated CSV files."""
    delimiter = str(',')
    quotechar = str('"')
    doublequote = True
    skipinitialspace = False
    lineterminator = str('\r\n')
    quoting = csv.QUOTE_MINIMAL

csv.register_dialect("csv", CsvDialect)
hashgen = Hashids(min_length=3)

class CsvImport():

    def __init__(self, multi_value_delimiter = ',', stdout = None):
        self.multi_value_delimiter = multi_value_delimiter
        self.stdout = stdout

    def print_out(self, msg, is_error = False):
        if self.stdout:
            self.stdout.write(msg + '\n')
        if is_error:
            logger.warning(msg)
        else:
            logger.info(msg)

class ResidentsCsvImport(CsvImport):
    FIELD_NAMES = (
        ('Residency Graduation Date', 'GraduationDate'),
        ('Residency Institution Name', 'ResidencyName'),
        ('NPI', 'NPI'),
        ('First Name', 'FirstName'),
        ('Last Name', 'LastName'),
        ('Degree (MD, DO)', 'Degree'),
        ('Email', 'Email'),
        ('extra', 'extra'),
    )
    RAW_FIELD_NAMES = [t[0] for t in FIELD_NAMES]
    FIELD_NAME_MAP = {t[0]:t[1] for t in FIELD_NAMES}

    def throwValueError(self, row, fieldName, value):
        error_msg = "Invalid {0} at row {1}: {2}".format(fieldName, row, value)
        raise ValueError(error_msg)

    def processFile(self, src_file, dry_run = False):
        num_existing = 0
        created = [] # list of Cases
        country_usa = Country.objects.get(code=Country.USA)

        # build lookup dicts
        qset = Degree.objects.all()
        degreeDict = {m.abbrev:m for m in qset}
        # qset = PracticeSpecialty.objects.all()
        # psDict = {m.name.upper():m for m in qset}
        # qset = SubSpecialty.objects.all()
        # subSpecDict = {m.name.upper():m for m in qset}
        # qset = State.objects.all()
        # stateDict = {m.abbrev:m for m in qset}
        # qset = User.objects.all()
        # usersDict = {u.email:u for u in qset}
        # qset = OrgGroup.objects.filter(organization = org)
        # groupsDict = {g.name:g for g in qset}
        # qset = LicenseType.objects.all()
        # licenseTypesDict = {g.name:g for g in qset}
        rp_ucsd = ResidencyProgram.objects.get(id=156)
        rp_uams = ResidencyProgram.objects.get(id=154)
        rp_maimonides = ResidencyProgram.objects.get(id=71)
        residency_map = {
            'UCSD': rp_ucsd,
            'UAMS': rp_uams,
            'Maimonides Medical Center': rp_maimonides
        }

        # qset = OrbitProcedure.objects.all()
        # proceduresDict = {p.name:p for p in qset}

        qset = Profile.objects.all().filter(npiNumber__isnull=False)
        profilesDict = {p.npiNumber:p for p in qset}

        try:
            reader = csv.DictReader(src_file, fieldnames=self.RAW_FIELD_NAMES, restkey='extra', dialect='csv')
            all_data = [row for row in reader]
            raw_data = all_data[1:]
            # pre-process 1: map to fieldnames and remove template data
            data = []
            for d in raw_data:
                if d['Residency Graduation Date'].strip() == '':
                    continue
                dd = {self.FIELD_NAME_MAP[key]:d[key] for key in d}
                data.append(dd)
            # pre-process 2: check valid FKs
            pos = 1
            for d in data:
                # map degree
                role = d['Degree'].strip().upper().replace('.','').replace(',','').replace('/','').replace('PHD','')
                d['Degree'] = degreeDict.get(role, None)

                d['ResidencyName'] = residency_map[d['ResidencyName']]

                if not d['Email']:
                    d['Email'] =  "{}.{}.{}@orbitcme.com".format(d['FirstName'],d['LastName'], hashgen.encode(pos))
                else:
                    d['Email'] = d['Email'].strip(' .')

                if len(d['GraduationDate']) == 4:
                    # fixing single year dates
                    d['GraduationDate'] = "06/30/{}".format(d['GraduationDate'])

                try:
                    d['GraduationDate'] = dparse(d['GraduationDate'])
                except ValueError as e:
                    self.throwValueError('GraduationDate', pos, d['GraduationDate'])

                npi = d['NPI'].strip()
                if npi not in profilesDict:
                    with transaction.atomic():
                        # Need to create a new user and profile for "historic" purposes?
                        # email =
                        profile = Profile.objects.createUserAndProfile(
                            d['Email'], '',
                            firstName=d['FirstName'],
                            lastName=d['LastName']
                        )
                        profile.country = country_usa
                        profile.npiNumber = npi
                        profile.residencyEndDate=d['GraduationDate']
                        profile.residency_program=d['ResidencyName']
                        if d['Degree']:
                            profile.degrees.set([d['Degree']])
                        profile.save()
                        d['profile'] = profile
                        msg = "Created Resident record: {FirstName} {LastName}, {Email}".format(**d)
                        self.print_out(msg)
                        created.append(profile)
                        pos += 1

            # final reporting
            # self.print_out('Num existing cases: {0}'.format(num_existing))
            # self.print_out('Num new cases: {0}'.format(num_new))
            self.print_out('Num profiles created: {0}'.format(len(created)))
            return True
        except csv.Error as e:
            error_msg = "CsvError: {0}".format(e)
            self.print_out(error_msg, True)
            return False
        except ValueError as e:
            error_msg = "ValueError: {0}".format(e)
            self.print_out(error_msg, True)
            return False

class Command(BaseCommand):
    help = "Process Residents roster."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('file', help='File to process')
        # parser.add_argument(
        #     '--dry_run',
        #     action='store_true',
        #     dest='dry_run',
        #     default=False,
        #     help='Dry run. Does not create any new members. Just print to console for debugging.'
        # )

    def handle(self, *args, **options):
        file = options['file']
        csv = ResidentsCsvImport()
        f = open(file, 'rt')
        success = csv.processFile(f)
