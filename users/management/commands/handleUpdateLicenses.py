import logging
from django.core.management.base import BaseCommand, CommandError
from users.license_tools import LicenseUpdater
from users.models import *
logger = logging.getLogger('mgmt.updlic')

class Command(BaseCommand):
    help = "Process uploaded csv file containing either State Licenses or DEA licenses for providers of a single organization."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('file_id', type=int,
                help='File ID of the uploaded CSV file to process')
        parser.add_argument('file_type',
                help='state or dea')
        parser.add_argument(
            '--dry_run',
            action='store_true',
            dest='dry_run',
            default=False,
            help='Dry run. Does not create or update any licenses. Just print to console for debugging.'
        )

    def handle(self, *args, **options):
        file_id = options['file_id']
        file_type = options['file_type'].lower()
        if file_type not in ('state','dea'):
            error_msg = "Invalid file_type: {0}".format(file_type)
            self.stderr.write(error_msg)
            return
        try:
            orgfile = OrgFile.objects.get(pk=file_id)
        except OrgFile.DoesNotExist:
            error_msg = "Invalid file_id: {0}".format(file_id)
            self.stderr.write(error_msg)
            return
        org = orgfile.organization
        src_file = orgfile.csvfile if orgfile.csvfile else orgfile.document
        self.stdout.write('Process file {0.name} for org: {0.organization} dry_run: {1}'.format(orgfile, options['dry_run']))
        licenseUpdater = LicenseUpdater(org, orgfile.user, options['dry_run'])
        success = licenseUpdater.processFile(options['file_type'], src_file)
        if not success:
            self.stderr.write('Process OrgFile failed')
            return
        # display data
        for pkey in licenseUpdater.profileDict:
            self.stdout.write("{0[0]} {0[1]} {0[2]}".format(pkey))
            profile = licenseUpdater.profileDict[pkey]
            userData = licenseUpdater.licenseData[profile.pk]
            for lkey in sorted(userData):
                self.stdout.write("   {0[0]:%Y-%m-%d} {0[1]} {0[2]}: {1}".format(lkey, userData[lkey]))
        if options['dry_run']:
            self.stdout.write('Dry run over')
            return
        orgfile.processed = True
        orgfile.save(update_fields=('processed',))
        self.stdout.write('OrgFile processed.')
