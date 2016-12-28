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
            4. One or more Degree
        """
        if not obj.contactEmail.endswith('gmail.com'):
            return False
        if not obj.country:
            return False
        if not obj.specialties.count():
            return False
        if not obj.degrees.count():
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
            'isNPIComplete',
            'isSignupComplete',
            'created',
            'modified'
        )

class CustomerSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    balance = serializers.ReadOnlyField()
    class Meta:
        model = Customer
        fields = (
            'id',
            'customerId',
            'balance',
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
    points = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, read_only=True)

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
            'points'
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

class CreateSRCmeOutSerializer(serializers.ModelSerializer):
    """Serializer for the response returned for create srcme entry"""
    documentUrl = serializers.FileField(source='document', max_length=None, use_url=True)

    class Meta:
        model = Entry
        fields = (
            'id',
            'documentUrl',
            'created',
            'success'
        )
    success = serializers.SerializerMethodField()

    def get_success(self, obj):
        return True

class UpdateSRCmeOutSerializer(serializers.ModelSerializer):
    """Serializer for the response returned for update srcme entry"""
    documentUrl = serializers.FileField(source='document', max_length=None, use_url=True)

    class Meta:
        model = Entry
        fields = (
            'id',
            'documentUrl',
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
    documentUrl = serializers.FileField(source='document', max_length=None, allow_empty_file=False, use_url=True)
    md5sum = serializers.ReadOnlyField()
    content_type = serializers.ReadOnlyField()
    tags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
        many=True,
        allow_null=True
    )
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
            'documentUrl',
            'md5sum',
            'content_type',
            'tags',
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


# Serializer for the combined fields of Entry + SRCme
# Used for both create and update
class SRCmeFormSerializer(serializers.Serializer):
    id = serializers.IntegerField(label='ID', read_only=True)
    activityDate = serializers.DateTimeField()
    description = serializers.CharField(max_length=500)
    fileMd5 = serializers.CharField(max_length=32, required=False)
    document = serializers.FileField(max_length=None, allow_empty_file=False, required=False)
    credits = serializers.DecimalField(max_digits=5, decimal_places=2, coerce_to_string=False)
    tags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
        many=True,
        required=False,
        allow_null=True
    )

    class Meta:
        fields = (
            'id',
            'activityDate',
            'description',
            'document',
            'fileMd5',
            'credits',
            'tags'
        )

    def validate(self, data):
        """
        Validate the client file_md5 matches server file_md5
        """
        #pprint(data)
        if 'document' in data and 'fileMd5' in data:
            client_md5 = data['fileMd5']
            server_md5 = md5_uploaded_file(data['document'])
            if client_md5 != server_md5:
                raise serializers.ValidationError('Check md5sum failed')
        return data

    def create(self, validated_data):
        """Create parent Entry and SRCme instances.
        It expects that View has passed the following keys to the serializer.save
        method, which then appear in validated_data:
            user: User instance
        """
        etype = EntryType.objects.get(name=ENTRYTYPE_SRCME)
        entry = Entry(
            entryType=etype,
            activityDate=validated_data.get('activityDate'),
            description=validated_data.get('description'),
            user=validated_data.get('user')
        )
        newDoc = validated_data.get('document', None) # UploadedFile (or subclass)
        if newDoc:
            logger.debug('uploaded filename: {0}'.format(newDoc.name))
            fileExt = os.path.splitext(newDoc.name)[1]
            fileMd5 = validated_data.get('fileMd5', '')
            if fileMd5:
                docName = fileMd5 + fileExt
            else:
                docName = newDoc.name
            entry.md5sum = fileMd5
            entry.content_type = newDoc.content_type
        entry.save()
        if newDoc:
            entry.document.save(docName.lower(), newDoc)
        # associate tags with saved entry
        tag_ids = validated_data.get('tags', [])
        if tag_ids:
            entry.tags.set(tag_ids)
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
        newDoc = validated_data.get('document', None)
        if newDoc:
            logger.debug('uploaded filename: {0}'.format(newDoc.name))
            fileExt = os.path.splitext(newDoc.name)[1]
            fileMd5 = validated_data.get('fileMd5', '')
            if fileMd5:
                docName = fileMd5 + fileExt
            else:
                docName = newDoc.name
            if entry.document:
                entry.document.delete()
            entry.document.save(docName.lower(), newDoc)
            entry.md5sum = fileMd5
            entry.content_type = newDoc.content_type
        entry.save()  # updates modified timestamp
        # replace old tags with new tags (wholesale)
        tag_ids = validated_data.get('tags', [])
        if tag_ids:
            entry.tags.set(tag_ids)
        instance.credits = validated_data.get('credits', instance.credits)
        instance.save()
        return instance

class PointTransactionSerializer(serializers.ModelSerializer):
    customerId = serializers.UUIDField(source='customer.customerId', format='hex_verbose', read_only=True)
    entry = serializers.PrimaryKeyRelatedField(allow_null=True, read_only=True)
    points = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, min_value=Decimal('1.0'), read_only=True)
    pricePaid = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, min_value=Decimal('0'), read_only=True)
    transactionId = serializers.ReadOnlyField()

    class Meta:
        model = PointTransaction
        fields = (
            'id',
            'customerId',
            'entry',
            'points',
            'pricePaid',
            'transactionId',
            'valid',
            'created',
            'modified'
        )


class PPOSerializer(serializers.ModelSerializer):
    points = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, min_value=Decimal('1.0'))
    price = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, min_value=Decimal('0.01'))
    class Meta:
        model = PointPurchaseOption
        fields = ('id', 'points', 'price')


class PROSerializer(serializers.ModelSerializer):
    points = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, min_value=Decimal('1.0'))
    class Meta:
        model = PointRewardOption
        fields = ('id', 'points', 'rewardType', 'description')


class UserFeedbackSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta:
        model = UserFeedback
        fields = ('id', 'user', 'message', 'hasBias', 'hasUnfairContent')
