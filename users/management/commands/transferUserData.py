import logging
import os
from hashids import Hashids
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from users.models import *

logger = logging.getLogger('mgmt.xferu')
hashgen = Hashids(salt=settings.DOCUMENT_HASHIDS_SALT, min_length=10)

class Command(BaseCommand):
    help = "Transfer offers/OrbitCME-entries/Self-Reported-entries from old user to new user. This is used when a provider started a new account and wants to transfer their data from their old account to the new account."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('old_email')
        parser.add_argument('new_email')

    def transferSREntry(entry):
        entry.user = self.toUser
        if entry.documents.exists():
            logger.info('Transfering documents for entry: {0}'.format(entry))
            old_docs = list(entry.documents.all())
            new_docs = []
            for m in old_docs:
                fd = m.document # the FileField (Note: fd.path is not supported for S3 storage)
                s = fd.url # the S3 url
                logger.info('Old docId: {0.pk} at: {0.document.url}'.format(m))
                # find the filename in the url path
                sc = s[0:s.find('?')]
                L = sc.rsplit('/',1)
                docName = L[1]
                logger.info('Filename: {0}'.format(docName))
                instance = Document(
                    md5sum=m.md5sum,
                    name=m.name,
                    content_type=m.content_type,
                    image_h=m.image_h,
                    image_w=m.image_w,
                    set_id=m.set_id,
                    user=self.toUser,
                    is_certificate=m.is_certificate
                )
                # save the file to new location (new user's folder), and save the instance
                instance.document.save(docName, m.document, save=True)
                instance.referenceId = 'document' + hashgen.encode(instance.pk)
                instance.save(update_fields=('referenceId',))
                logger.info('New docId: {0.pk} at: {0.document.url}'.format(instance))
                new_docs.append(instance)
            for m in old_docs:
                m.document.delete(save=True)
                m.delete()
            entry.documents.set(new_docs) # update entry.documents
        entry.save(update_fields=('user',))
        msg = " - Transferred sr-cme entry {0.pk}".format(entry)
        self.stdout.write(msg)
        logger.info(msg)
        return entry

    def transferEntries(self):
        """Transfer entries from self.fromUser to self.toUser
        Entry-types handled:
            sr-cme (and documents transferred to toUser)
            br-cme (and redeemed offer transferred to toUser)
        If other Entrytypes are used in the future, then new code should be added
          to handle the entry transfer to another user.
        Returns: tuple (updated_srcme:list of entries, updated_brcme:list of entries)
        """
        entries = Entry.objects.select_related('entryType').filter(user=self.fromUser).order_by('-created')
        updated_srcme = []
        updated_brcme = []
        for entry in entries:
            if entry.entryType.name == ENTRYTYPE_SRCME:
                transferSREntry(entry)
                updated_srcme.append(entry)
                continue
            if entry.entryType.name == ENTRYTYPE_BRCME:
                try:
                    offer = OrbitCmeOffer.objects.get(pk=entry.brcme.offerId)
                except OrbitCmeOffer.DoesNotExist:
                    msg = '! No offer found for {0.brcme.offerId}'.format(entry)
                    self.stdout.write(msg)
                    logger.warning(msg)
                else:
                    offer.user = self.toUser
                    offer.save(update_fields=('user',))
                entry.user = self.toUser
                entry.save(update_fields=('user',))
                msg = ' - Transferred br-cme entry: {0.pk}'.format(entry)
                self.stdout.write(msg)
                logger.info(msg)
                updated_brcme.append(entry)
        return (updated_srcme, updated_brcme)

    def transferUnredeemedOffers(self):
        """Transfer un-redeemed offers from self.fromUser to self.toUser
        For each offer:
            check if user already has an offer for the article before transferring
        """
        transferred = []
        dups = [] # list of offers that were not transferred b/c toUser already has an offer for the article
        offers = OrbitCmeOffer.objects.filter(user=self.fromUser, redeemed=False).order_by('pk')
        for offer in offers:
            # does user already have an offer for this aurl
            aurl = offer.url
            qs = OrbitCmeOffer.objects.filter(user=self.toUser, url=aurl, valid=True)
            if qs.exists():
                # toUser already has an offer for this aurl. Add old offer to duplicates
                dups.append(offer)
                msg = "Skip transfer offer {0.pk}|{0} because it would create a duplicate.".format(offer)
                self.stdout.write(msg)
                logger.warning(msg)
                continue
            # can transfer offer
            offer.user = self.toUser
            offer.save(update_fields=('user',))
            transferred.append(offer)
        return (transferred, dups)

    def handle(self, *args, **options):
        old_email = options['old_email']
        new_email = options['new_email']
        if not User.objects.filter(email=old_email).exists():
            raise ValueError('Invalid old_email. User does not exist.')
            return
        self.fromUser = User.objects.get(email=old_email)
        if not User.objects.filter(email=new_email).exists():
            raise ValueError('Invalid new_email. User does not exist.')
            return
        self.toUser = User.objects.get(email=new_email)
        msg = "Confirm transfer user data from {0}/{0.profile} to {1}/{1.profile}. Type y to continue: ".format(self.fromUser, self.toUser)
        val = input(msg)
        if val.lower() != 'y':
            self.stdout.write('Exiting.')
            return
        # transfer entries
        self.stdout.write('Transferring feed entries...')
        updated_srcme, updated_brcme = self.transferEntries()
        msg = "Number of Self-reported entries transferred: {0}".format(len(updated_srcme))
        self.stdout.write(msg)
        logger.info(msg)
        msg = "Number of OrbitCME entries transferred: {0}".format(len(updated_brcme))
        self.stdout.write(msg)
        logger.info(msg)
        # transfer un-redeemed offers
        self.stdout.write('Transferring un-redeemed offers...')
        transferred, dups = self.transferUnredeemedOffers()
        msg = "Number of un-redeemed offers transferred: {0}".format(len(transferred))
        self.stdout.write(msg)
        logger.info(msg)
        msg = "Number of duplicate offers not transferred: {0}".format(len(dups))
        self.stdout.write(msg)
        logger.info(msg)
        self.stdout.write('Done.')
        # Note: this does not transfer Certificates/AuditReports because they are generated files,
        #  The user should generate new Certs/ARs as needed from their new user account.
