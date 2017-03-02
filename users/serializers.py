from datetime import timedelta
from decimal import Decimal
from cStringIO import StringIO
import os
import hashlib
import logging
import mimetypes
from PIL import Image
from pprint import pprint
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework import serializers
from common.viewutils import newUuid, md5_uploaded_file
from .models import *

logger = logging.getLogger(__name__)

class DegreeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Degree
        fields = ('id', 'abbrev', 'name')

class CmeTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = CmeTag
        fields = ('id', 'name', 'priority', 'description')

class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ('id', 'code', 'name')

class PracticeSpecialtyListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PracticeSpecialty
        fields = ('id', 'name')

class PracticeSpecialtySerializer(serializers.ModelSerializer):
    cmeTags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.exclude(name=CMETAG_SACME),
        many=True,
        allow_null=True
    )
    class Meta:
        model = PracticeSpecialty
        fields = ('id', 'name', 'cmeTags')


class ProfileSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    socialId = serializers.ReadOnlyField()
    inviteId = serializers.ReadOnlyField()
    verified = serializers.ReadOnlyField()
    cmeTags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
        many=True,
        allow_null=True
    )
    degrees = serializers.PrimaryKeyRelatedField(
        queryset=Degree.objects.all(),
        many=True,
        allow_null=True
    )
    specialties = serializers.PrimaryKeyRelatedField(
        queryset=PracticeSpecialty.objects.all(),
        many=True,
        allow_null=True
    )
    country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        allow_null=True
    )
    isSignupComplete = serializers.SerializerMethodField()
    isNPIComplete = serializers.SerializerMethodField()

    def get_isSignupComplete(self, obj):
        """Signup is complete if the following fields are populated
            1. contactEmail is a gmail address
            2. Country is provided
            3. One or more PracticeSpecialty
            4. One or more Degree (now called primaryRole in UI, and only 1 selection allowed...)
            5. user has saved a UserSubscription
        """
        if not obj.contactEmail.endswith('gmail.com'):
            return False
        if not obj.country:
            return False
        if not obj.specialties.count():
            return False
        if not obj.degrees.count():
            return False
        if not obj.user.subscriptions.exists():
            return False
        return True

    def get_isNPIComplete(self, obj):
        """
        True: obj.shouldReqNPINumber is False
        True: If obj.shouldReqNPINumber and npiNumber is non-blank.
        False: If obj.shouldReqNPINumber and npiNumber is blank.
        """
        if obj.shouldReqNPINumber():
            #print('shouldReqNPINumber is True!')
            #print('npiNumber: {0}'.format(obj.npiNumber))
            if obj.npiNumber:
                return True
            return False
        #print('shouldReqNPINumber is False')
        return True

    class Meta:
        model = Profile
        fields = (
            'id',
            'firstName',
            'lastName',
            'contactEmail',
            'country',
            'jobTitle',
            'description',
            'inviteId',
            'socialId',
            'npiNumber',
            'cmeTags',
            'degrees',
            'specialties',
            'verified',
            'cmeDuedate',
            'isNPIComplete',
            'isSignupComplete',
            'created',
            'modified'
        )

    def update(self, instance, validated_data):
        """
        1. If contactEmail changed and profile is already verified:
            then reset verified to False
        2. If any new specialties added, then check for new cmeTags.
            Note: this only adds new tags to profile, it does not remove
            any old tags b/c they can be associated with user's feed entries
            and hence needed by the Dashboard.
        """
        reset_verify = False
        upd_cmetags = False
        newEmail = validated_data.get('contactEmail', None)
        if newEmail and newEmail != instance.contactEmail and instance.verified:
            reset_verify = True
        pracSpecs = validated_data.get('specialties', [])
        tag_ids = set([t.pk for t in instance.cmeTags.all()])
        for ps in pracSpecs:
            logger.debug(ps.name)
            for t in ps.cmeTags.all():
                if t.pk not in tag_ids:
                    tag_ids.add(t.pk)
                    logger.debug('New profile.cmeTag: {0}'.format(t))
                    upd_cmetags = True
        instance = super(ProfileSerializer, self).update(instance, validated_data)
        if upd_cmetags:
            instance.cmeTags.set(list(tag_ids))
        if reset_verify:
            instance.verified = False
            instance.save()
            logger.debug('reset profile.verified for {0}'.format(instance.contactEmail))
        return instance

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

class BrowserCmeOfferSerializer(serializers.ModelSerializer):
    userId = serializers.IntegerField(source='user.id', read_only=True)
    activityDate = serializers.ReadOnlyField()
    url = serializers.ReadOnlyField()
    pageTitle = serializers.ReadOnlyField()
    expireDate = serializers.ReadOnlyField()
    credits = serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=False, read_only=True)
    sponsorId = serializers.PrimaryKeyRelatedField(source='sponsor.id', read_only=True)
    logo_url = serializers.URLField(source='sponsor.logo_url', max_length=1000, read_only=True)

    class Meta:
        model = BrowserCmeOffer
        fields = (
            'id',
            'userId',
            'activityDate',
            'url',
            'pageTitle',
            'expireDate',
            'credits',
            'sponsorId',
            'logo_url'
        )

class SponsorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sponsor
        fields = ('id', 'name', 'logo_url')

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
            'is_thumb'
        )
        read_only_fields = ('name','md5sum','content_type','image_h','image_w', 'is_thumb')


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
    sponsorId = serializers.PrimaryKeyRelatedField(source='sponsor.id', read_only=True)
    logo_url = serializers.URLField(source='sponsor.logo_url', max_length=1000, read_only=True)
    tags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
        many=True,
        allow_null=True
    )
    documents = DocumentReadSerializer(many=True, required=False)
    extra = serializers.SerializerMethodField()

    def get_extra(self, obj):
        etype = obj.entryType.name
        if etype == ENTRYTYPE_SRCME:
            s = SRCmeSubSerializer(obj.srcme)
        elif etype == ENTRYTYPE_BRCME:
            s = BRCmeSubSerializer(obj.brcme)
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
            'extra',
            'sponsorId',
            'logo_url',
            'created',
            'modified'
        )


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
        queryset=CmeTag.objects.all(),
        many=True,
        required=False,
        allow_null=True
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

    def validate(self, data):
        """Check offer is not expired"""
        offer = data.get('offerId', None)
        logger.debug('validate offer: {0}'.format(offer.pk))
        if offer is not None and hasattr(offer, 'expireDate') and (offer.expireDate < timezone.now()):
            return serializers.ValidationError('The offerId {0} has already expired'.format(offer.pk))
        return data

    def create(self, validated_data):
        """Create parent Entry and BrowserCme instances.
        Note: this expects that View has passed the following
        keys to serializer.save which then appear in validated_data:
            user: User instance
        """
        etype = EntryType.objects.get(name=ENTRYTYPE_BRCME)
        offer = validated_data['offerId']
        entry = Entry.objects.create(
            entryType=etype,
            sponsor=offer.sponsor,
            activityDate=offer.activityDate,
            description=validated_data.get('description'),
            user=validated_data.get('user')
        )
        # associate tags with saved entry
        tag_ids = validated_data.get('tags', [])
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
        queryset=CmeTag.objects.all(),
        many=True,
        required=False,
        allow_null=True
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

    class Meta:
        fields = (
            'document',
            'fileMd5',
            'name',
            'image_h',
            'image_w'
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
                logger.debug('UploadDocument: Image open failed: {0}'.format(str(e)))
            else:
                set_id = newUuid()
        instance = Document(
            md5sum = fileMd5,
            content_type = newDoc.content_type,
            name=validated_data.get('name', ''),
            image_h=image_h,
            image_w=image_w,
            set_id=set_id,
            user=validated_data.get('user')
        )
        # Save the file, and save the model instance
        instance.document.save(docName.lower(), newDoc, save=True)
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
                user=validated_data.get('user')
            )
            # Save the thumb file, and save the model instance
            memory_file.seek(0)
            cf = ContentFile(memory_file.getvalue()) # Create a ContentFile from the memory_file
            thumb_instance.document.save(thumbName.lower(), cf, save=True)
        return instance

# Serializer for the combined fields of Entry + SRCme
# Used for both create and update
class SRCmeFormSerializer(serializers.Serializer):
    id = serializers.IntegerField(label='ID', read_only=True)
    activityDate = serializers.DateTimeField()
    description = serializers.CharField(max_length=500)
    credits = serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=False)
    tags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
        many=True,
        required=False,
        allow_null=True
    )
    documents = serializers.PrimaryKeyRelatedField(
        queryset=Document.objects.all(),
        many=True,
        required=False,
        allow_null=True
    )

    class Meta:
        fields = (
            'id',
            'activityDate',
            'description',
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
        entry = Entry(
            entryType=etype,
            activityDate=validated_data.get('activityDate'),
            description=validated_data.get('description'),
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


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, min_value=Decimal('0.01'))
    displayMonthlyPrice = serializers.SerializerMethodField()

    def get_displayMonthlyPrice(self, obj):
        """Returns True if the price should be divided by 12 to be displayed as a monthly price.
        2017-02-28: changed to False per Ram
        """
        return False

    class Meta:
        model = SubscriptionPlan
        fields = (
            'id',
            'planId',
            'name',
            'price',
            'trialDays',
            'billingCycleMonths',
            'displayMonthlyPrice',
            'active',
            'created',
            'modified'
        )

class SubscriptionPlanPublicSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, read_only=True)
    displayMonthlyPrice = serializers.SerializerMethodField()

    def get_displayMonthlyPrice(self, obj):
        """Returns True if the price should be divided by 12 to be displayed as a monthly price.
        2017-02-28: changed to False per Ram
        """
        return False

    class Meta:
        model = SubscriptionPlan
        fields = (
            'price',
            'displayMonthlyPrice',
            'trialDays',
        )


class UserSubscriptionSerializer(serializers.ModelSerializer):
    subscriptionId = serializers.ReadOnlyField()
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    plan = serializers.PrimaryKeyRelatedField(read_only=True)
    status = serializers.ReadOnlyField()
    display_status = serializers.ReadOnlyField()
    billingFirstDate = serializers.ReadOnlyField()
    billingStartDate = serializers.ReadOnlyField()
    billingEndDate = serializers.ReadOnlyField()

    class Meta:
        model = UserSubscription
        fields = (
            'id',
            'subscriptionId',
            'user',
            'plan',
            'status',
            'display_status',
            'billingFirstDate',
            'billingStartDate',
            'billingEndDate',
            'created',
            'modified'
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
        required=False,
        allow_null=True
    )
    class Meta:
        model = EligibleSite
        fields = (
            'id',
            'domain_name',
            'domain_title',
            'example_url',
            'example_title',
            'description',
            'specialties'
        )
