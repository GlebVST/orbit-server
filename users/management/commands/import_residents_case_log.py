from __future__ import unicode_literals
import logging
import csv
import re
from time import sleep
from io import StringIO
from dateutil.parser import parse as dparse
from django.core.management import BaseCommand
from django.db import transaction, IntegrityError

from users.models import Profile
from users.models.residents import OrbitProcedure, Case, OrbitProcedureMatch

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

class ResidentsCaseLogCsvImport(CsvImport):
    FIELD_NAMES = (
        ('Date-Time', 'timestamp'),
        ('NPI', 'npi'),
        ('Procedure Name', 'procedure'),
        ("CPT", 'cpt_code'),
        ('Adult\Child', 'age_category'),
        ('Facility ID', 'facility'),
        ('extra', 'extra'),
    )
    RAW_FIELD_NAMES = [t[0] for t in FIELD_NAMES]
    FIELD_NAME_MAP = {t[0]:t[1] for t in FIELD_NAMES}

    def throwValueError(self, row, fieldName, value):
        error_msg = "Invalid {0} at row {1}: {2}".format(fieldName, row, value)
        raise ValueError(error_msg)

    def processFile(self, src_file, facility, dry_run = False):
        created = [] # list of Cases

        qset = OrbitProcedureMatch.objects.filter(facility__iexact=facility)
        procedureRegexDict = {p.regex:p for p in qset}

        qset = Profile.objects.all().filter(npiNumber__isnull=False)
        profilesDict = {p.npiNumber:p for p in qset}

        try:
            f = StringIO(src_file.read())
            reader = csv.DictReader(f, fieldnames=self.RAW_FIELD_NAMES, restkey='extra', dialect='csv')
            all_data = [row for row in reader]
            raw_data = all_data[1:]
            # pre-process 1: map to fieldnames and remove template data
            data = []
            for d in raw_data:
                if d['Date-Time'].strip() == '':
                    continue
                dd = {self.FIELD_NAME_MAP[key]:d[key] for key in d}
                data.append(dd)
            # pre-process 2: check valid FKs
            pos = 1
            for d in data:

                if not d.get('age_category'):
                    self.throwValueError(pos, 'Age Category', d['age_category'])

                d['age_category'] = d['age_category'].strip().upper()

                # map procedure name to model reference
                procedure = d['procedure'].strip()
                d['procedure_name'] = procedure

                procedureMatch = next((rx for rx in procedureRegexDict if re.match(rx, procedure)), None)

                # if not procedureMatch:
                #     self.throwValueError('Procedure Name', pos, procedure)
                if procedureMatch:
                    d['procedure'] = procedureRegexDict[procedureMatch].procedure
                else:
                    d['procedure'] = None


                try:
                    d['timestamp'] = dparse(d['timestamp'])
                except ValueError as e:
                    self.throwValueError('Date-Time', pos, d['timestamp'])

                npi = d['npi'].strip()
                if npi in profilesDict:
                    d['profile'] = profilesDict[npi]

                d['facility'] = facility

                pos += 1

            for c in data:
                c.pop('extra')
                try:
                    with transaction.atomic():
                        case = Case.objects.create(**c)
                        created.append(case)
                        msg = "Created Case record: {npi} {cpt_code}, {timestamp}".format(**c)
                        self.print_out(msg)
                except IntegrityError as e:
                    self.print_out(e)

            # final reporting
            # self.print_out('Num existing cases: {0}'.format(num_existing))
            # self.print_out('Num new cases: {0}'.format(num_new))
            self.print_out('Num cases created: {0}'.format(len(created)))
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
    help = "Process Residents case log file."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('file', help='File to process')
        parser.add_argument('facility', help='Source Facility')
        # parser.add_argument(
        #     '--dry_run',
        #     action='store_true',
        #     dest='dry_run',
        #     default=False,
        #     help='Dry run. Does not create any new members. Just print to console for debugging.'
        # )

    def handle(self, *args, **options):
        file = options['file']
        facility = options['facility']
        csv = ResidentsCaseLogCsvImport()
        f = open(file, 'rt')
        success = csv.processFile(f, facility)
