"""Transfer entries from one user account to another. This is used
when a user decides to start a new subscription under a new email
address, but wants to transfer his entries from his old account to
his new one
TODO: make this a management command
"""
from users.models import *
from hashids import Hashids
import logging

logger = logging.getLogger('mgmt.xferu')
hashgen = Hashids(salt=settings.DOCUMENT_HASHIDS_SALT, min_length=10)

def transferSREntry(entry, fromUser, toUser):
    entry.user = toUser
    if entry.documents.exists():
        print('Transfering documents for entry: {0}'.format(entry))
        old_docs = list(entry.documents.all())
        new_docs = []
        for m in old_docs:
            fd = m.document # the FileField (Note: fd.path is not supported for S3 storage)
            s = fd.url # the S3 url
            print('Old docId: {0.pk} at: {0.document.url}'.format(m))
            # find the filename in the url path
            sc = s[0:s.find('?')]
            L = sc.rsplit('/',1)
            docName = L[1]
            print('Filename: {0}'.format(docName))
            instance = Document(
                md5sum=m.md5sum,
                name=m.name,
                content_type=m.content_type,
                image_h=m.image_h,
                image_w=m.image_w,
                set_id=m.set_id,
                user=toUser,
                is_certificate=m.is_certificate
            )
            # save the file to new location (new user's folder), and save the instance
            instance.document.save(docName, m.document, save=True)
            instance.referenceId = 'document' + hashgen.encode(instance.pk)
            instance.save(update_fields=('referenceId',))
            print('New docId: {0.pk} at: {0.document.url}'.format(instance))
            logger.info('New docId: {0.pk} at: {0.document.url}'.format(instance))
            new_docs.append(instance)
        for m in old_docs:
            m.document.delete(save=True)
            m.delete()
        entry.documents.set(new_docs) # update entry.documents
    entry.save(update_fields=('user',))
    print('Updated srcme entry: {0}'.format(entry))
    logger.info('Updated srcme entry: {0.pk}'.format(entry))
    return entry

def transferEntries(fromUser, toUser):
    """Transfer entries and offers from fromUser to toUser"""
    entries = Entry.objects.select_related('entryType').filter(user=fromUser).order_by('-created')
    updated = []
    for entry in entries:
        if entry.entryType.name == ENTRYTYPE_SRCME:
            transferSREntry(entry, fromUser, toUser)
            updated.append(entry)
            continue
        if entry.entryType.name == ENTRYTYPE_BRCME:
            try:
                offer = OrbitCmeOffer.objects.get(pk=entry.brcme.offerId)
            except OrbitCmeOffer.DoesNotExist:
                logger.warning('No offer found for {0.brcme.offerId}'.format(entry))
                print('No offer found for {0.brcme.offerId}'.format(entry))
            else:
                offer.user = toUser
                offer.save(update_fields=('user',))
                print('Updated offer: {0}'.format(offer))
        entry.user = toUser
        entry.save(update_fields=('user',))
        print('Updated brcme entry: {0}'.format(entry))
        logger.info('Updated brcme entry: {0.pk}'.format(entry))
        updated.append(entry)
    return updated
