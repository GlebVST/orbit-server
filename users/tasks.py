"""Celery tasks for users app"""
import logging
from celery import shared_task
import pytz
from smtplib import SMTPException
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import get_template
from django.utils import timezone
from .models import OrgFile
from .license_tools import LicenseUpdater
from .emailutils import makeSubject, setCommonContext

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
        licenseUpdater.src_file = orgfile.document
        licenseUpdater.fileType = orgfile.file_type
        parseErrors = licenseUpdater.extractData() # sets licenseUpdater.data
        licenseUpdater.validateUsers() # sets profileDict
        preprocessStats = licenseUpdater.preprocessData() # dict(num_new, num_upd, num_no_action, num_error)
        num_action, num_errors = licenseUpdater.processData()
        logger.info('Num create_errors: {0}'.format(len(licenseUpdater.create_errors)))
        logger.info('Num update_errors: {0}'.format(len(licenseUpdater.update_errors)))
        orgfile.processed = True
        orgfile.save(update_fields=('processed',))
        result_stats = {
            'num_no_action': preprocessStats['num_no_action'],
            'num_action': num_action
        }
        # send EmailMessage
        from_email = settings.SUPPORT_EMAIL
        if settings.ENV_TYPE == settings.ENV_PROD:
            to_email = [orgfile.user.email, settings.SUPPORT_EMAIL]
            bcc_email = [tup[1] for tup in settings.ADMINS]
        else:
            to_email = [tup[1] for tup in settings.ADMINS]
            bcc_email = []
        subject = makeSubject('[Orbit] Process License File Results')
        ctx = {
            'orgfile': orgfile,
            'stats': result_stats,
            'num_errors': num_errors, # computed by processData
            'create_errors': licenseUpdater.create_errors,
            'update_errors': licenseUpdater.update_errors
        }
        setCommonContext(ctx)
        message = get_template('email/process_license_file_results.html').render(ctx)
        msg = EmailMessage(subject,
                message,
                to=to_email,
                bcc=bcc_email,
                from_email=from_email)
        msg.content_subtype = 'html'
        try:
            msg.send()
        except SMTPException as e:
            logException(logger, request, 'UploadLicense send email failed.')
