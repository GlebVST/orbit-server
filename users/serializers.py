from datetime import timedelta
from decimal import Decimal
import os
import logging
from pprint import pprint
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import serializers
from common.viewutils import md5_uploaded_file
from .models import *

logger = logging.getLogger(__name__)

class DegreeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Degree
        fields = ('id', 'abbrev', 'name')

class PracticeSpecialtySerializer(serializers.ModelSerializer):
    class Meta:
        model = PracticeSpecialty
        fields = ('id', 'name')

class CmeTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = CmeTag
        fields = ('id', 'name', 'priority', 'description')

class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ('id', 'code', 'name')

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
            'isNPIComplete',
            'isSignupComplete',
            'created',
            'modified'
        )

    def update(self, instance, validated_data):
        """If contactEmail changed and profile is already verified, then reset verified to False"""
        reset_verify = False
        newEmail = validated_data.get('contactEmail', None)
        if newEmail and newEmail != instance.contactEmail and instance.verified:
            reset_verify = True
        instance = super(ProfileSerializer, self).update(instance, validated_data)
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

    class Meta:
        model = BrowserCmeOffer
        fields = (
            'id',
            'userId',
            'activityDate',
            'url',
            'pageTitle',
            'expireDate',
            'credits'
        )

class EntryTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntryType
        fields = ('id', 'name','description')

# intended to be used by SerializerMethodField on EntrySerializer
class RewardSubSerializer(serializers.ModelSerializer):
    rewardType = serializers.ReadOnlyField()
    points = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, read_only=True)
    class Meta:
        model = Reward
        fields = (
            'rewardType',
            'points'
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
class ExpiredBRCmeSubSerializer(serializers.ModelSerializer):
    offer = serializers.PrimaryKeyRelatedField(read_only=True)
    credits = serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=False, read_only=True)
    url = serializers.ReadOnlyField()
    pageTitle = serializers.ReadOnlyField()
    expireDate = serializers.ReadOnlyField()

    class Meta:
        model = ExBrowserCme
        fields = (
            'offer',
            'credits',
            'url',
            'pageTitle',
            'expireDate'
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
    tags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
        many=True,
        allow_null=True
    )
    documents = DocumentReadSerializer(many=True, required=False)
    extra = serializers.SerializerMethodField()

    def get_extra(self, obj):
        etype = obj.entryType.name
        if etype == ENTRYTYPE_REWARD:
            s = RewardSubSerializer(obj.reward)
        elif etype == ENTRYTYPE_BRCME:
            s = BRCmeSubSerializer(obj.brcme)
        elif etype == ENTRYTYPE_SRCME:
            s = SRCmeSubSerializer(obj.srcme)
        elif etype == ENTRYTYPE_EXBRCME:
            s = ExpiredBRCmeSubSerializer(obj.exbrcme)
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
        # replace old tags with new tags (wholesale)
        tag_ids = validated_data.get('tags', [])
        if tag_ids:
            entry.tags.set(tag_ids)
        instance.purpose = validated_data.get('purpose', instance.purpose)
        instance.planEffect = validated_data.get('planEffect', instance.planEffect)
        instance.save()
        return instance


class UploadDocumentSerializer(serializers.Serializer):
    document = serializers.FileField(max_length=None, allow_empty_file=False)
    fileMd5 = serializers.CharField(max_length=32)
    uploadId = serializers.CharField(max_length=36)
    name = serializers.CharField(max_length=255, required=False)
    image_h = serializers.IntegerField(min_value=0, required=False)
    image_w = serializers.IntegerField(min_value=0, required=False)

    class Meta:
        fields = (
            'document',
            'fileMd5',
            'uploadId',
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
        logger.debug('uploaded filename: {0}'.format(newDoc.name))
        fileExt = os.path.splitext(newDoc.name)[1]
        fileMd5 = validated_data['fileMd5']
        docName = fileMd5 + fileExt
        instance = Document(
            document=newDoc,
            md5sum = fileMd5,
            content_type = newDoc.content_type,
            uploadId=validated_data['uploadId'],
            name=validated_data.get('name', ''),
            image_h=validated_data.get('image_h', None),
            image_w=validated_data.get('image_w', None),
            user=validated_data.get('user')
        )
        # Save the file, and save the model instance
        instance.document.save(docName.lower(), newDoc, save=True)
        return instance

# Serializer for the combined fields of Entry + SRCme
# Used for both create and update
class SRCmeFormSerializer(serializers.Serializer):
    id = serializers.IntegerField(label='ID', read_only=True)
    activityDate = serializers.DateTimeField()
    description = serializers.CharField(max_length=500)
    # uploadId: used by create to associate Documents with entry
    uploadId = serializers.CharField(max_length=36, required=False)
    credits = serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=False)
    tags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
        many=True,
        required=False,
        allow_null=True
    )
    # used by update to update the document_set
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
            'uploadId',
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
        uploadId = validated_data.get('uploadId')
        entry = Entry(
            entryType=etype,
            activityDate=validated_data.get('activityDate'),
            description=validated_data.get('description'),
            user=user
        )
        entry.save()
        # associate tags with saved entry
        tag_ids = validated_data.get('tags', [])
        if tag_ids:
            entry.tags.set(tag_ids)
        # associate documents with saved entry using uploadId
        if uploadId:
            documents = Document.objects.filter(user=user, uploadId=uploadId)
            num_docs = documents.count()
            if num_docs:
                logger.debug('Associating {0} documents with entry'.format(num_docs))
                entry.documents.set(documents)
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
    class Meta:
        model = SubscriptionPlan
        fields = (
            'id',
            'planId',
            'name',
            'price',
            'trialDays',
            'billingCycleMonths',
            'active',
            'created',
            'modified'
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
