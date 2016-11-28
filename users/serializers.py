from datetime import timedelta
from decimal import Decimal
import os
from pprint import pprint
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import serializers
from common.viewutils import md5_uploaded_file
from .models import *

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
        fields = ('id', 'name')


class ProfileSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    socialUrl = serializers.ReadOnlyField()
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

    class Meta:
        model = Profile
        fields = (
            'id',
            'firstName',
            'lastName',
            'jobTitle',
            'description',
            'npiNumber',
            'inviteId',
            'socialUrl',
            'pictureUrl',
            'cmeTags',
            'degrees',
            'specialties',
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
            'contactEmail',
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
    tags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
        many=True,
        allow_null=False
    )
    class Meta:
        model = SRCme
        fields = (
            'credits',
            'tags'
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

class EntryReadSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id', read_only=True)
    entryType = serializers.PrimaryKeyRelatedField(read_only=True)
    documentUrl = serializers.FileField(source='document', max_length=None, allow_empty_file=True, use_url=True)
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
            'activityDate',
            'description',
            'documentUrl',
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

    class Meta:
        fields = (
            'id',
            'offerId',
            'description',
            'purpose',
            'planEffect'
        )

    def validate(self, data):
        """Check offer is not expired"""
        offer = data.get('offerId', None)
        print('validate offer: {0}'.format(offer.pk))
        if offer is not None and hasattr(offer, 'expireDate') and (offer.expireDate < timezone.now()):
            return serializers.ValidationError('The offerId {offerId} has already expired'.format(**data))
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

    class Meta:
        fields = (
            'id',
            'description',
            'purpose',
            'planEffect'
        )

    def update(self, instance, validated_data):
        entry = instance.entry
        entry.description = validated_data.get('description', entry.description)
        entry.save() # updates modified timestamp
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
        many=True,
        queryset=CmeTag.objects.all()
    )

    class Meta:
        fields = (
            'id',
            'activityDate',
            'description',
            'document',
            'credits',
            'tags'
        )

    def validate(self, data):
        """
        Validate the client file_md5 matches server file_md5
        """
        pprint(data)
        if 'document' in data and 'fileMd5' in data:
            print('Verifying fileMd5')
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
        entry = Entry.objects.create(
            entryType=etype,
            activityDate=validated_data.get('activityDate'),
            description=validated_data.get('description'),
            user=validated_data.get('user')
        )
        newDoc = validated_data.get('document', None) # UploadedFile (or subclass)
        if newDoc:
            print('uploaded filename: {0}'.format(newDoc.name))
            fileExt = os.path.splitext(newDoc.name)[1]
            fileMd5 = validated_data.get('fileMd5', '')
            if fileMd5:
                docName = fileMd5 + fileExt
            else:
                docName = newDoc.name
            entry.document.save(docName.lower(), newDoc)
        # Using parent entry, create SRCme instance
        instance = SRCme.objects.create(
            entry=entry,
            credits=validated_data.get('credits')
        )
        tag_ids = validated_data.get('tags', [])
        if tag_ids:
            instance.tags.set(tag_ids)
        return instance

    def update(self, instance, validated_data):
        #entry = Entry.objects.get(pk=instance.pk)
        entry = instance.entry
        entry.activityDate = validated_data.get('activityDate', entry.activityDate)
        entry.description = validated_data.get('description', entry.description)
        newDoc = validated_data.get('document', None)
        if newDoc:
            print('uploaded filename: {0}'.format(newDoc.name))
            fileExt = os.path.splitext(newDoc.name)[1]
            fileMd5 = validated_data.get('fileMd5', '')
            if fileMd5:
                docName = fileMd5 + fileExt
            else:
                docName = newDoc.name
            if entry.document:
                entry.document.delete()
            entry.document.save(docName.lower(), newDoc)
        entry.save()  # updates modified timestamp
        instance.credits = validated_data.get('credits', instance.credits)
        tag_ids = validated_data.get('tags', [])
        if tag_ids:
            instance.tags.set(tag_ids)
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
