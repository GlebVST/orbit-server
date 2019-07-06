"""Celery tasks for users app"""
import logging
from celery import shared_task
from django.utils import timezone
from .models import OrgFile
from .license_tools import LicenseUpdater

logger = logging.getLogger('gen.tasks')

@shared_task
def add(x, y):
    """For debugging"""
    #print('add {0} + {1}'.format(x,y))
    return x + y


@shared_task
def processValidatedLicenseFile(orgfile_pk):
    """Process a validated DEA/StateLicense OrgFile. It calls licenseUpdater.processData to update the db
    Args:
        orgfile_pk: int OrgFile pkeyid
    After processing the file, it sets orgfile.processed to True.
    """
    logger.info('processValidatedLicenseFile for: {0} start'.format(orgfile_pk))
    try:
        orgfile = OrgFile.objects.get(pk=orgfile_pk)
    except OrgFile.DoesNotExist:
        logger.error('processValidatedLicenseFile: OrgFile does not exist for id: {0}'.format(orgfile_pk))
    else:
        if not orgfile.isValidFileTypeForUpdate():
            logger.error('processValidatedLicenseFile: OrgFile {0.pk} has wrong file_type for this operation: {0.file_type}. Exiting.'.format(orgfile))
            return
        if not orgfile.validated:
            logger.error('processValidatedLicenseFile: OrgFile {0.pk} is not validated. Exiting.'.format(orgfile))
            return
        if orgfile.processed:
            logger.error('processValidatedLicenseFile: OrgFile {0.pk} is already processed. Exiting.'.format(orgfile))
            return
        licenseUpdater = LicenseUpdater(orgfile.organization, orgfile.user, dry_run=False)
        parseErrors = licenseUpdater.extractData() # sets licenseUpdater.data
        licenseUpdater.validateUsers() # sets profileDict
        stats = licenseUpdater.preprocessData() # dict(num_new, num_upd, num_no_action, num_error)
        num_errors = licenseUpdater.processData()
        logger.info('Num create_errors: {0}'.format(len(licenseUpdater.create_errors)))
        logger.info('Num update_errors: {0}'.format(len(licenseUpdater.update_errors)))
        orgfile.processed = True
        orgfile.save(update_fields=('processed',))
