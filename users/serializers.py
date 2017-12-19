from datetime import timedelta
from decimal import Decimal
from cStringIO import StringIO
from hashids import Hashids
import os
import hashlib
import logging
import mimetypes
from PIL import Image
from urlparse import urlparse, urldefrag
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework import serializers
from common.viewutils import newUuid, md5_uploaded_file
from .models import *

logger = logging.getLogger('gen.srl')

class DegreeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Degree
        fields = ('id', 'abbrev', 'name', 'sort_order')

class CmeTagWithSpecSerializer(serializers.ModelSerializer):
    specialties = serializers.PrimaryKeyRelatedField(
        queryset=PracticeSpecialty.objects.all(),
        many=True
    )
    class Meta:
        model = CmeTag
        fields = ('id', 'name', 'priority', 'description', 'specialties')

class CmeTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = CmeTag
        fields = ('id', 'name', 'priority', 'description')

# Used by auth_view to serialize the SA-CME tag
class ActiveCmeTagSerializer(serializers.ModelSerializer):
    is_active = serializers.SerializerMethodField()

    def get_is_active(self, obj):
        return True

    class Meta:
        model = CmeTag
        fields = ('id', 'name', 'priority', 'description', 'is_active')


class NestedStateSerializer(serializers.ModelSerializer):

    class Meta:
        model = State
        fields = ('id', 'abbrev', 'name', 'rnCertValid')

class CountrySerializer(serializers.ModelSerializer):
    states = NestedStateSerializer(many=True, read_only=True)

    class Meta:
        model = Country
        fields = ('id', 'code', 'name', 'states')

class StateSerializer(serializers.ModelSerializer):
    country = serializers.PrimaryKeyRelatedField(queryset=Country.objects.all())

    class Meta:
        model = State
        fields = ('id', 'country', 'abbrev', 'name', 'rnCertValid')

class PracticeSpecialtyListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PracticeSpecialty
        fields = ('id', 'name')

class PracticeSpecialtySerializer(serializers.ModelSerializer):
    cmeTags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.exclude(name=CMETAG_SACME),
        many=True
    )
    class Meta:
        model = PracticeSpecialty
        fields = ('id', 'name', 'cmeTags')

class ProfileCmetagSerializer(serializers.ModelSerializer):
    """Used by ReadProfileSerializer and UpdateProfileSerializer"""
    id = serializers.ReadOnlyField(source='tag.id')
    name = serializers.ReadOnlyField(source='tag.name')
    priority = serializers.ReadOnlyField(source='tag.priority')
    description = serializers.ReadOnlyField(source='tag.description')

    class Meta:
        model = ProfileCmetag
        fields = ('id', 'name', 'priority', 'description', 'is_active')

class UpdateProfileCmetagSerializer(serializers.ModelSerializer):
    tag = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.exclude(name=CMETAG_SACME))
    is_active = serializers.BooleanField()

    class Meta:
        model = ProfileCmetag
        fields = ('tag','is_active')

class ManageProfileCmetagSerializer(serializers.Serializer):
    """Updates the is_active flag of a list of existing ProfileCmetags for a given user"""
    tags = UpdateProfileCmetagSerializer(many=True)

    def update(self, instance, validated_data):
        data = validated_data['tags']
        for d in data:
            t = d['tag']
            is_active = d['is_active']
            try:
                pct = ProfileCmetag.objects.get(profile=instance, tag=t)
            except ProfileCmetag.DoesNotExist:
                logger.warning('ManageProfileCmeTags: Invalid tag for user {0}: {1}'.format(instance.user, t))
            else:
                if pct.is_active != is_active:
                    pct.is_active = is_active
                    pct.save()
                    logger.info('Updated ProfileCmetag {0}'.format(pct))
        return instance

class UpdateProfileSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    degrees = serializers.PrimaryKeyRelatedField(
        queryset=Degree.objects.all(),
        many=True
    )
    specialties = serializers.PrimaryKeyRelatedField(
        queryset=PracticeSpecialty.objects.all(),
        many=True
    )
    country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        allow_null=True
    )
    cmeTags = serializers.SerializerMethodField()
    isSignupComplete = serializers.SerializerMethodField()
    isNPIComplete = serializers.SerializerMethodField()

    def get_isSignupComplete(self, obj):
        return obj.isSignupComplete()

    def get_isNPIComplete(self, obj):
        return obj.isNPIComplete()

    def get_cmeTags(self, obj):
        qset = ProfileCmetag.objects.filter(profile=obj)
        return [ProfileCmetagSerializer(m).data for m in qset]

    class Meta:
        model = Profile
        fields = (
            'id',
            'firstName',
            'lastName',
            'contactEmail',
            'country',
            'jobTitle',
            'inviteId',
            'socialId',
            'pictureUrl',
            'npiNumber',
            'npiFirstName',
            'npiLastName',
            'npiType',
            'nbcrnaId',
            'cmeTags',
            'degrees',
            'specialties',
            'verified',
            'accessedTour',
            'cmeStartDate',
            'cmeEndDate',
            'isNPIComplete',
            'isSignupComplete',
            'created',
            'modified'
        )
        read_only_fields = (
            'cmeTags',
            'inviteId',
            'socialId',
            'pictureUrl',
            'verified',
            'accessedTour',
            'created',
            'modified'
        )

    def update(self, instance, validated_data):
        """
        If any new specialties added, then check for new cmeTags.
        If a specialty is removed, then remove its cmeTags if not assigned to
        any entry made by the user.
        """
        user = instance.user
        upd_cmetags = False
        tag_ids = None
        del_tagids = set() # tagids to delete
        new_tagids = set() # tagids to add
        # get current specialties before updating the instance
        curSpecs = set([ps for ps in instance.specialties.all()])
        # update the instance
        instance = super(UpdateProfileSerializer, self).update(instance, validated_data)
        # now handle cmeTags
        spec_key = 'specialties'
        if spec_key in validated_data:
            # need to check if key exists, because a PATCH request may not contain the spec_key
            pracSpecs = validated_data[spec_key]
            newSpecs = set([ps for ps in pracSpecs])
            newly_added_specs = newSpecs.difference(curSpecs)
            del_specs = curSpecs.difference(newSpecs)
            for ps in del_specs:
                logger.info('User {0.email} : remove ps: {1.name}'.format(user, ps))
                for t in ps.cmeTags.all():
                    pct_qset = ProfileCmetag.objects.filter(profile=instance, tag=t)
                    if pct_qset.exists():
                        pct = pct_qset[0]
                        num_entries = t.entries.filter(user=user).count()
                        #logger.debug('Num entries for tag {0} = {1}'.format(t, num_entries))
                        if num_entries == 0:
                            pct.delete()
                            logger.info('Delete unused ProfileCmetag: {0}'.format(pct))
                        elif pct.is_active:
                            # Set is_active to false
                            pct.is_active = False
                            pct.save()
                            logger.info('Inactivate ProfileCmetag: {0}'.format(pct))
            # get refreshed set
            tag_ids = set([t.pk for t in instance.cmeTags.all()])
            for ps in newly_added_specs:
                logger.info('User {0.email} : Add ps: {1.name}'.format(user, ps))
                for t in ps.cmeTags.all():
                    # tag may already exist from a previous occasion in which ps was assigned to user
                    pct, created = ProfileCmetag.objects.get_or_create(profile=instance, tag=t)
                    if created:
                        logger.info('New ProfileCmetag: {0}'.format(pct))
                    elif not pct.is_active:
                        pct.is_active = True
                        pct.save()
                        logger.info('Re-activate ProfileCmetag: {0}'.format(pct))
        return instance


class ReadProfileSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    # degrees and specialties are list of pkeyids
    degrees = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    specialties = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    country = serializers.PrimaryKeyRelatedField(read_only=True)
    isSignupComplete = serializers.SerializerMethodField()
    isNPIComplete = serializers.SerializerMethodField()
    cmeTags = serializers.SerializerMethodField()

    def get_isSignupComplete(self, obj):
        return obj.isSignupComplete()

    def get_isNPIComplete(self, obj):
        return obj.isNPIComplete()

    def get_cmeTags(self, obj):
        qset = ProfileCmetag.objects.filter(profile=obj)
        return [ProfileCmetagSerializer(m).data for m in qset]

    class Meta:
        model = Profile
        fields = (
            'id',
            'firstName',
            'lastName',
            'contactEmail',
            'country',
            'jobTitle',
            'inviteId',
            'socialId',
            'pictureUrl',
            'npiNumber',
            'npiFirstName',
            'npiLastName',
            'npiType',
            'nbcrnaId',
            'cmeTags',
            'degrees',
            'specialties',
            'verified',
            'accessedTour',
            'cmeStartDate',
            'cmeEndDate',
            'isNPIComplete',
            'isSignupComplete',
            'created',
            'modified'
        )
        read_only_fields = fields


class CustomerSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    class Meta:
        model = Customer
        fields = (
            'id',
            'customerId',
            'created',
            'modified'
        )
        read_only_fields = fields

class StateLicenseSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    state = serializers.PrimaryKeyRelatedField(queryset=State.objects.all())
    license_type = serializers.StringRelatedField(read_only=True)
    class Meta:
        model = StateLicense
        fields = ('id','user', 'state', 'license_type', 'license_no', 'expiryDate')


# Entire offer is read-only because offers are created by the plugin server.
# A separate serializer exists to redeem the offer (and create br-cme entry in the user's feed).
class BrowserCmeOfferSerializer(serializers.ModelSerializer):
    userId = serializers.IntegerField(source='user.id', read_only=True)
    credits = serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=False, read_only=True)
    sponsor = serializers.PrimaryKeyRelatedField(read_only=True)
    logo_url = serializers.URLField(source='sponsor.logo_url', max_length=1000, read_only=True, default='')
    cmeTags = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = BrowserCmeOffer
        fields = (
            'id',
            'userId',
            'activityDate',
            'url',
            'pageTitle',
            'suggestedDescr',
            'expireDate',
            'credits',
            'sponsor',
            'logo_url',
            'cmeTags'
        )
        read_only_fields = fields

class SponsorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sponsor
        fields = ('id', 'abbrev', 'name', 'logo_url')

class EntryTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntryType
        fields = ('id', 'name','description')


# intended to be used by SerializerMethodField on EntrySerializer
class NotificationSubSerializer(serializers.ModelSerializer):
    expireDate = serializers.ReadOnlyField()
    class Meta:
        model = Notification
        fields = (
            'expireDate',
        )

# intended to be used by SerializerMethodField on EntrySerializer
class SRCmeSubSerializer(serializers.ModelSerializer):
    credits = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False)
    class Meta:
        model = SRCme
        fields = (
            'credits',
        )

# intended to be used by SerializerMethodField on EntrySerializer
class BRCmeSubSerializer(serializers.ModelSerializer):
    offer = serializers.PrimaryKeyRelatedField(read_only=True)
    credits = serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=False, read_only=True)
    url = serializers.ReadOnlyField()
    pageTitle = serializers.ReadOnlyField()
    purpose = serializers.ReadOnlyField()
    planEffect = serializers.ReadOnlyField()

    class Meta:
        model = BrowserCme
        fields = (
            'offer',
            'credits',
            'url',
            'pageTitle',
            'purpose',
            'planEffect'
        )

# intended to be used by SerializerMethodField on EntrySerializer
class StoryCmeSubSerializer(serializers.ModelSerializer):
    story = serializers.PrimaryKeyRelatedField(read_only=True)
    credits = serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=False, read_only=True)
    url = serializers.ReadOnlyField()
    title = serializers.ReadOnlyField()

    class Meta:
        model = StoryCme
        fields = (
            'story',
            'credits',
            'url',
            'title'
        )


class DocumentReadSerializer(serializers.ModelSerializer):
    url = serializers.FileField(source='document', max_length=None, allow_empty_file=False, use_url=True)
    class Meta:
        model = Document
        fields = (
            'id',
            'url',
            'name',
            'md5sum',
            'content_type',
            'image_h',
            'image_w',
            'is_thumb',
            'is_certificate'
        )
        read_only_fields = ('name','md5sum','content_type','image_h','image_w', 'is_thumb','is_certificate')


class CreateSRCmeOutSerializer(serializers.ModelSerializer):
    """Serializer for the response returned for create srcme entry"""
    documents = DocumentReadSerializer(many=True, required=False)

    class Meta:
        model = Entry
        fields = (
            'id',
            'documents',
            'created',
            'success'
        )
    success = serializers.SerializerMethodField()

    def get_success(self, obj):
        return True

class UpdateSRCmeOutSerializer(serializers.ModelSerializer):
    """Serializer for the response returned for update srcme entry"""
    documents = DocumentReadSerializer(many=True, required=False)

    class Meta:
        model = Entry
        fields = (
            'id',
            'documents',
            'modified',
            'success'
        )
    success = serializers.SerializerMethodField()

    def get_success(self, obj):
        return True

class EntryReadSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id', read_only=True)
    entryTypeId = serializers.PrimaryKeyRelatedField(source='entryType.id', read_only=True)
    entryType = serializers.StringRelatedField(read_only=True)
    sponsor = serializers.PrimaryKeyRelatedField(read_only=True)
    logo_url = serializers.URLField(source='sponsor.logo_url', max_length=1000, read_only=True, default='')
    tags = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    documents = DocumentReadSerializer(many=True, required=False)
    creditType = serializers.ReadOnlyField(source='ama_pra_catg')
    extra = serializers.SerializerMethodField()

    def get_extra(self, obj):
        etype = obj.entryType.name
        if etype == ENTRYTYPE_BRCME:
            s = BRCmeSubSerializer(obj.brcme)
        elif etype == ENTRYTYPE_SRCME:
            s = SRCmeSubSerializer(obj.srcme)
        elif etype == ENTRYTYPE_STORY_CME:
            s = StoryCmeSubSerializer(obj.storycme)
        else:
            s = NotificationSubSerializer(obj.notification)
        return s.data  # <class 'rest_framework.utils.serializer_helpers.ReturnDict'>

    class Meta:
        model = Entry
        fields = (
            'id',
            'user',
            'entryType',
            'entryTypeId',
            'activityDate',
            'description',
            'tags',
            'documents',
            'creditType',
            'extra',
            'sponsor',
            'logo_url',
            'created',
            'modified'
        )
        read_only_fields = fields

# Serializer for Create BrowserCme entry
class BRCmeCreateSerializer(serializers.Serializer):
    id = serializers.IntegerField(label='ID', read_only=True)
    description = serializers.CharField(max_length=500)
    purpose = serializers.IntegerField(min_value=0, max_value=1)
    planEffect = serializers.IntegerField(min_value=0, max_value=1)
    offerId = serializers.PrimaryKeyRelatedField(
        queryset=BrowserCmeOffer.objects.filter(redeemed=False)
    )
    tags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.exclude(name=CMETAG_SACME),
        many=True,
        required=False
    )

    class Meta:
        fields = (
            'id',
            'offerId',
            'description',
            'purpose',
            'planEffect',
            'tags'
        )

    def create(self, validated_data):
        """Create parent Entry and BrowserCme instances.
        Note: this expects the following keys in validated_data:
            user: User instance
        2017-07-05: If offer.eligible_site is associated with only 1 PracSpec,
        and this specialty is contained in user.specialties, then add its
        named cmeTag to the tags for this entry.
        """
        etype = EntryType.objects.get(name=ENTRYTYPE_BRCME)
        offer = validated_data['offerId']
        user=validated_data.get('user')
        entry = Entry.objects.create(
            entryType=etype,
            sponsor=offer.sponsor,
            activityDate=offer.activityDate,
            description=validated_data.get('description'),
            ama_pra_catg=Entry.CREDIT_CATEGORY_1,
            user=user
        )
        # associate tags with saved entry
        tag_ids = validated_data.get('tags', [])
        num_specialties = offer.eligible_site.specialties.count()
        if num_specialties == 1:
            spec = offer.eligible_site.specialties.first()
            if user.profile.specialties.filter(pk=spec.pk).exists():
                try:
                    spec_tag = CmeTag.objects.get(name=spec.name)
                except CmeTag.DoesNotExist:
                    pass
                else:
                    if spec_tag.pk not in tag_ids:
                        tag_ids.append(spec_tag.pk)
        if tag_ids:
            entry.tags.set(tag_ids)
        # Using parent entry, create BrowserCme instance
        instance = BrowserCme.objects.create(
            entry=entry,
            offer=offer,
            purpose=validated_data.get('purpose'),
            planEffect=validated_data.get('planEffect'),
            url=offer.url,
            pageTitle=offer.pageTitle,
            credits=offer.credits
        )
        return instance

# Serializer for Update BrowserCme entry
class BRCmeUpdateSerializer(serializers.Serializer):
    id = serializers.IntegerField(label='ID', read_only=True)
    description = serializers.CharField(max_length=500)
    purpose = serializers.IntegerField(min_value=0, max_value=1)
    planEffect = serializers.IntegerField(min_value=0, max_value=1)
    tags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.exclude(name=CMETAG_SACME),
        many=True,
        required=False
    )

    class Meta:
        fields = (
            'id',
            'description',
            'purpose',
            'planEffect',
            'tags'
        )

    def update(self, instance, validated_data):
        entry = instance.entry
        entry.description = validated_data.get('description', entry.description)
        entry.save() # updates modified timestamp
        # if tags key is present: replace old with new (wholesale)
        if 'tags' in validated_data:
            tag_ids = validated_data['tags']
            if tag_ids:
                entry.tags.set(tag_ids)
            else:
                entry.tags.set([])
        instance.purpose = validated_data.get('purpose', instance.purpose)
        instance.planEffect = validated_data.get('planEffect', instance.planEffect)
        instance.save()
        return instance


class UploadDocumentSerializer(serializers.Serializer):
    document = serializers.FileField(max_length=None, allow_empty_file=False)
    fileMd5 = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=255, required=False)
    image_h = serializers.IntegerField(min_value=0, required=False)
    image_w = serializers.IntegerField(min_value=0, required=False)
    is_certificate = serializers.BooleanField()

    class Meta:
        fields = (
            'document',
            'fileMd5',
            'name',
            'image_h',
            'image_w',
            'is_certificate'
        )

    def validate(self, data):
        """
        Validate the client file_md5 matches server file_md5
        """
        if 'document' in data and 'fileMd5' in data:
            client_md5 = data['fileMd5']
            server_md5 = md5_uploaded_file(data['document'])
            if client_md5 != server_md5:
                raise serializers.ValidationError('Check md5sum failed')
        return data

    def create(self, validated_data):
        """Create Document instance.
        It expects that View has passed the following keys to the serializer.save
        method, which then appear in validated_data:
            user: User instance
        """
        hashgen = Hashids(salt=settings.DOCUMENT_HASHIDS_SALT, min_length=10)
        newDoc = validated_data['document'] # UploadedFile (or subclass)
        fileName = validated_data.get('name', '')
        logger.debug('uploaded filename: {0}'.format(fileName))
        basename, fileExt = os.path.splitext(fileName)
        fileMd5 = validated_data['fileMd5']
        docName = fileMd5 + fileExt
        image_h=validated_data.get('image_h', None)
        image_w=validated_data.get('image_w', None)
        set_id = ''
        thumb_size = 200
        thumbMd5 = None
        is_image = newDoc.content_type.lower().startswith('image')
        if is_image:
            try:
                im = Image.open(newDoc)
                image_w, image_h = im.size
                if image_w > thumb_size or image_h > thumb_size:
                    logger.debug('Creating thumbnail: {0}'.format(fileName))
                    im.thumbnail((thumb_size, thumb_size), Image.ANTIALIAS)
                    mime = mimetypes.guess_type(fileName)
                    plain_ext = mime[0].split('/')[1]
                    memory_file = StringIO()
                    # save thumb to memory_file
                    im.save(memory_file, plain_ext, quality=90)
                    # calculate md5sum of thumb
                    thumbMd5 = hashlib.md5(memory_file.getvalue()).hexdigest()
            except IOError, e:
                logger.exception('UploadDocument: Image open failed.')
            else:
                set_id = newUuid()
        instance = Document(
            md5sum = fileMd5,
            content_type = newDoc.content_type,
            name=validated_data.get('name', ''),
            image_h=image_h,
            image_w=image_w,
            set_id=set_id,
            user=validated_data.get('user'),
            is_certificate=validated_data.get('is_certificate')
        )
        # Save the file, and save the model instance
        instance.document.save(docName.lower(), newDoc, save=True)
        instance.referenceId = 'document' + hashgen.encode(instance.pk)
        instance.save(update_fields=('referenceId',))
        # Save thumbnail instance
        if thumbMd5:
            thumbName = thumbMd5 + fileExt
            thumb_instance = Document(
                md5sum = thumbMd5,
                content_type = newDoc.content_type,
                name=instance.name,
                image_h=thumb_size,
                image_w=thumb_size,
                set_id=set_id,
                is_thumb=True,
                user=validated_data.get('user'),
                is_certificate=validated_data.get('is_certificate')
            )
            # Save the thumb file, and save the model instance
            memory_file.seek(0)
            cf = ContentFile(memory_file.getvalue()) # Create a ContentFile from the memory_file
            thumb_instance.document.save(thumbName.lower(), cf, save=True)
            thumb_instance.referenceId = 'document' + hashgen.encode(thumb_instance.pk)
            thumb_instance.save(update_fields=('referenceId',))
        return instance

# Serializer for the combined fields of Entry + SRCme
# Used for both create and update
class SRCmeFormSerializer(serializers.Serializer):
    id = serializers.IntegerField(label='ID', read_only=True)
    activityDate = serializers.DateTimeField()
    description = serializers.CharField(max_length=500)
    creditType = serializers.CharField(max_length=2)
    credits = serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=False)
    tags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
        many=True,
        required=False
    )
    documents = serializers.PrimaryKeyRelatedField(
        queryset=Document.objects.all(),
        many=True,
        required=False
    )

    class Meta:
        fields = (
            'id',
            'activityDate',
            'description',
            'creditType',
            'credits',
            'tags',
            'documents'
        )

    def create(self, validated_data):
        """Create parent Entry and SRCme instances.
        It expects that View has passed the following keys to the serializer.save
        method, which then appear in validated_data:
            user: User instance
        """
        etype = EntryType.objects.get(name=ENTRYTYPE_SRCME)
        user = validated_data['user']
        creditType = validated_data.get('creditType', Entry.CREDIT_CATEGORY_1)
        entry = Entry(
            entryType=etype,
            activityDate=validated_data.get('activityDate'),
            description=validated_data.get('description'),
            ama_pra_catg=creditType,
            user=user
        )
        entry.save()
        # associate tags with saved entry
        tags = validated_data.get('tags', [])
        if tags:
            entry.tags.set(tags)
        # associate documents with saved entry
        docs = validated_data.get('documents', [])
        if docs:
            entry.documents.set(docs)
        # Using parent entry, create SRCme instance
        instance = SRCme.objects.create(
            entry=entry,
            credits=validated_data.get('credits')
        )
        return instance

    def update(self, instance, validated_data):
        #entry = Entry.objects.get(pk=instance.pk)
        entry = instance.entry
        entry.activityDate = validated_data.get('activityDate', entry.activityDate)
        entry.description = validated_data.get('description', entry.description)
        entry.ama_pra_catg = validated_data.get('creditType', entry.ama_pra_catg)
        entry.save()  # updates modified timestamp
        # if tags key is present: replace old with new (wholesale)
        if 'tags' in validated_data:
            tag_ids = validated_data['tags']
            if tag_ids:
                entry.tags.set(tag_ids)
            else:
                entry.tags.set([])
        if 'documents' in validated_data:
            currentDocs = entry.documents.all()
            current_doc_ids = set([m.pk for m in currentDocs])
            #logger.debug(current_doc_ids)
            docs = validated_data['documents']
            doc_ids = [m.pk for m in docs]
            #logger.debug(doc_ids)
            if doc_ids:
                # are there any docs to delete
                delete_doc_ids = current_doc_ids.difference(set(doc_ids))
                for docid in delete_doc_ids:
                    m = Document.objects.get(pk=docid)
                    logger.debug('updateSRCme: delete document {0}'.format(m))
                    m.document.delete()
                    m.delete()
                # associate entry with docs
                entry.documents.set(doc_ids)
            else:
                entry.documents.set([])
        instance.credits = validated_data.get('credits', instance.credits)
        instance.save()
        return instance


DISPLAY_PRICE_AS_MONTHLY = True

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, min_value=Decimal('0.01'))
    discountPrice = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False)
    displayMonthlyPrice = serializers.SerializerMethodField()

    def get_displayMonthlyPrice(self, obj):
        """Returns True if the price should be divided by 12 to be displayed as a monthly price."""
        return DISPLAY_PRICE_AS_MONTHLY

    class Meta:
        model = SubscriptionPlan
        fields = (
            'id',
            'planId',
            'name',
            'price',
            'discountPrice',
            'trialDays',
            'billingCycleMonths',
            'displayMonthlyPrice',
            'active',
            'created',
            'modified'
        )

class SubscriptionPlanPublicSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, read_only=True)
    discountPrice = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, read_only=True)
    displayMonthlyPrice = serializers.SerializerMethodField()

    def get_displayMonthlyPrice(self, obj):
        """Returns True if the price should be divided by 12 to be displayed as a monthly price."""
        return DISPLAY_PRICE_AS_MONTHLY

    class Meta:
        model = SubscriptionPlan
        fields = (
            'name',
            'price',
            'discountPrice',
            'displayMonthlyPrice',
            'trialDays',
        )


class ReadUserSubsSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    plan = serializers.PrimaryKeyRelatedField(read_only=True)
    plan_name = serializers.ReadOnlyField(source='plan.name')
    bt_status = serializers.ReadOnlyField(source='status')
    class Meta:
        model = UserSubscription
        fields = (
            'id',
            'subscriptionId',
            'user',
            'plan',
            'plan_name',
            'bt_status',
            'display_status',
            'billingFirstDate',
            'billingStartDate',
            'billingEndDate',
            'created',
            'modified'
        )
        read_only_fields = fields


class CreateUserSubsSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(
        queryset=SubscriptionPlan.objects.all())
    payment_method_token = serializers.CharField(max_length=64)
    invitee_discount = serializers.BooleanField()
    convertee_discount = serializers.BooleanField()
    trial_duration = serializers.IntegerField(required=False)

    def save(self, **kwargs):
        """This expects user passed in to kwargs
        Call Manager method UserSubscription createBtSubscription
        with the following parameters:
            plan_id: BT planId of plan
            payment_method_token:str for Customer
            trial_duration:int number of days of trial (if not given, use plan default)
            invitee_discount:bool - used for InvitationDiscount
            convertee_discount:bool - used for AffiliatePayout
        Returns: tuple (result object, UserSubscription instance)
        """
        user = kwargs['user']
        validated_data = self.validated_data
        plan = validated_data['plan']
        payment_method_token = validated_data['payment_method_token']
        invitee_discount = validated_data['invitee_discount']
        convertee_discount = validated_data['convertee_discount']
        subs_params = {
            'plan_id': plan.planId,
            'payment_method_token': payment_method_token,
            'invitee_discount': invitee_discount,
            'convertee_discount': convertee_discount
        }
        key = 'trial_duration'
        if key in validated_data:
            subs_params[key] = validated_data[key]
        return UserSubscription.objects.createBtSubscription(user, plan, subs_params)

class UpgradePlanSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(
        queryset=SubscriptionPlan.objects.all())
    payment_method_token = serializers.CharField(max_length=64)

    def save(self, **kwargs):
        """This expects user_subs passed into kwargs for the existing
        UserSubscription to be canceled.
        It calls UserSusbscription manager method upgradePlan.
        Returns: tuple (result object, UserSubscription instance)
        """
        user_subs = kwargs['user_subs'] # existing user_subs on old plan
        validated_data = self.validated_data
        plan = validated_data['plan']
        payment_method_token = validated_data['payment_method_token']
        return UserSubscription.objects.upgradePlan(user_subs, plan, payment_method_token)


SACME_LABEL = 'Self-Assessed CME'

class StorySerializer(serializers.ModelSerializer):
    sponsor = serializers.PrimaryKeyRelatedField(read_only=True)
    logo_url = serializers.URLField(source='sponsor.logo_url', max_length=1000, read_only=True, default='')
    displayLabel = serializers.SerializerMethodField()

    def get_displayLabel(self, obj):
        return SACME_LABEL

    class Meta:
        model = Story
        fields = (
            'id',
            'title',
            'description',
            'startDate',
            'expireDate',
            'launch_url',
            'sponsor',
            'logo_url',
            'displayLabel'
        )


# Note: this will not be used for Orbit Stories as it has been superseded by the Story model.
# It will be changed at a later date to be used for personalized PinnedMessages.
class PinnedMessageSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    sponsor = serializers.PrimaryKeyRelatedField(read_only=True)
    logo_url = serializers.URLField(source='sponsor.logo_url', max_length=1000, read_only=True, default='')
    displayLabel = serializers.SerializerMethodField()

    def get_displayLabel(self, obj):
        return SACME_LABEL

    class Meta:
        model = PinnedMessage
        fields = (
            'id',
            'user',
            'title',
            'description',
            'startDate',
            'expireDate',
            'launch_url',
            'sponsor',
            'logo_url',
            'displayLabel'
        )

class UserFeedbackSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta:
        model = UserFeedback
        fields = ('id', 'user', 'message', 'hasBias', 'hasUnfairContent')

class EligibleSiteSerializer(serializers.ModelSerializer):
    specialties = serializers.PrimaryKeyRelatedField(
        queryset=PracticeSpecialty.objects.all(),
        many=True,
        required=False
    )
    needs_ad_block = serializers.BooleanField(default=False)
    all_specialties = serializers.BooleanField(default=False)
    is_unlisted = serializers.BooleanField(default=False)
    class Meta:
        model = EligibleSite
        fields = (
            'id',
            'domain_name',
            'domain_title',
            'example_url',
            'example_title',
            'description',
            'specialties',
            'all_specialties',
            'needs_ad_block',
            'is_unlisted'
        )

    def create(self, validated_data):
        """Create EligibleSite instance
        Add example_url.netloc to AllowedHost
        Add example_url to AllowedUrl
        """
        instance = super(EligibleSiteSerializer, self).create(validated_data)
        example_url = urldefrag(validated_data['example_url'])[0]
        res = urlparse(example_url)
        netloc = res.netloc
        # create AllowedHost
        host, created = AllowedHost.objects.get_or_create(hostname=netloc)
        if created:
            logger.info('EligibleSite: new AllowedHost: {0}'.format(netloc))
        # create AllowedUrl
        allowed_url, created = AllowedUrl.objects.get_or_create(
            host=host,
            eligible_site=instance,
            url=example_url,
            page_title=validated_data.get('example_title'),
            abstract=''
        )
        if created:
            logger.info('EligibleSite: new AllowedUrl: {0.url}'.format(allowed_url))
        return instance


class CertificateReadSerializer(serializers.ModelSerializer):
    url = serializers.FileField(source='document', max_length=None, allow_empty_file=False, use_url=True)
    tag = serializers.PrimaryKeyRelatedField(queryset=CmeTag.objects.all())
    state_license = serializers.PrimaryKeyRelatedField(queryset=StateLicense.objects.all())
    class Meta:
        model = Certificate
        fields = (
            'referenceId',
            'url',
            'name',
            'startDate',
            'endDate',
            'credits',
            'tag',
            'state_license',
            'created'
        )
        read_only_fields = fields


class StateLicenseSubSerializer(serializers.ModelSerializer):
    state = serializers.StringRelatedField(read_only=True)
    license_type = serializers.StringRelatedField(read_only=True)
    class Meta:
        model = StateLicense
        fields = ('state','license_type', 'license_no', 'expiryDate')

class AuditReportReadSerializer(serializers.ModelSerializer):
    npiNumber = serializers.ReadOnlyField(source='user.profile.npiNumber')
    nbcrnaId = serializers.ReadOnlyField(source='user.profile.nbcrnaId')
    degree = serializers.SerializerMethodField()
    statelicense = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()

    def get_degree(self, obj):
        return obj.user.profile.formatDegrees()

    def get_statelicense(self, obj):
        user = obj.user
        if user.statelicenses.exists():
            s =  StateLicenseSubSerializer(user.statelicenses.all()[0])
            return s.data
        return None

    def get_country(self, obj):
        """After upgrade to DRF 3.7, use SerializerMethodField because profile.country can be null
        """
        p = obj.user.profile
        if p.country:
            return p.country.code
        return None

    class Meta:
        model = AuditReport
        fields = (
            'referenceId',
            'name',
            'npiNumber',
            'nbcrnaId',
            'country',
            'degree',
            'statelicense',
            'startDate',
            'endDate',
            'saCredits',
            'otherCredits',
            'data',
            'created'
        )
        read_only_fields = fields


class ReadInvitationDiscountSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='invitee.id', read_only=True)
    inviter = serializers.PrimaryKeyRelatedField(read_only=True)
    inviteeEmail = serializers.ReadOnlyField(source='invitee.email')
    inviteeFirstName = serializers.ReadOnlyField(source='invitee.profile.firstName')
    inviteeLastName = serializers.ReadOnlyField(source='invitee.profile.lastName')
    isComplete = serializers.SerializerMethodField()
    creditAmount = serializers.SerializerMethodField()

    def get_isComplete(self, obj):
        """Instance is complete if inviterDiscount is set
            (e.g. invitee begun Active subscription)
        """
        return obj.inviterDiscount is not None

    def get_creditAmount(self, obj):
        if obj.inviterDiscount and obj.creditEarned:
            return obj.inviterDiscount.amount
        return 0

    class Meta:
        model = UserFeedback
        fields = (
            'id',
            'inviter',
            'inviteeEmail',
            'inviteeFirstName',
            'inviteeLastName',
            'isComplete',
            'creditAmount',
            'created',
            'modified'
        )
        read_only_fields = fields
