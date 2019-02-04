import logging
from django.core.management.base import BaseCommand, CommandError
from users.csv_tools import ProviderCsvImport
from users.models import (
        OrgFile,
    )
logger = logging.getLogger('mgmt.orgfile')

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

    def handle(self, *args, **options):
        file_id = options['file_id']
        try:
            orgfile = OrgFile.objects.get(pk=file_id)
        except OrgFile.DoesNotExist:
            error_msg = "Invalid file_id: {0}".format(file_id)
            self.stderr.write(error_msg)
            return
        org = orgfile.organization
        self.stdout.write('Pre-process roster file for {0.code}: checking validity...'.format(org))
        src_file = orgfile.csvfile if orgfile.csvfile else orgfile.document

        csv = ProviderCsvImport(stdout=self.stdout)
        success = csv.processOrgFile(org.id, src_file, options['dry_run'], options['test_ticket'])
        if success and not options['dry_run']:
            orgfile.processed = True
            orgfile.save(update_fields=('processed',))
