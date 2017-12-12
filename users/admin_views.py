"""Read-only views to enable admin staff to view data for other users"""
from django.utils import timezone
from rest_framework import generics, exceptions, permissions, status, serializers
from rest_framework.pagination import PageNumberPagination
from oauth2_provider.ext.rest_framework import TokenHasReadWriteScope, TokenHasScope
# app
from .models import *
from .serializers import CmeTagSerializer, DegreeSerializer, CountrySerializer, PracticeSpecialtyListSerializer

class ReadProfileListSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id')
    email = serializers.EmailField(source='user.email')

    class Meta:
        model = Profile
        fields = (
            'id',
            'email',
            'firstName',
            'lastName',
            'verified',
        )
        read_only_fields = fields

class ReadProfileDetailSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id')
    email = serializers.EmailField(source='user.email')
    cmeTags = CmeTagSerializer(many=True)
    degrees = DegreeSerializer(many=True)
    specialties = PracticeSpecialtyListSerializer(many=True)
    country = CountrySerializer()
    subscriptionStatus = serializers.SerializerMethodField()

    def get_subscriptionStatus(self, obj):
        user = obj.user
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        if user_subs:
            return user_subs.display_status
        return 'No Subscription'

    class Meta:
        model = Profile
        fields = (
            'id',
            'email',
            'firstName',
            'lastName',
            'country',
            'inviteId',
            'socialId',
            'npiNumber',
            'npiFirstName',
            'npiLastName',
            'npiType',
            'cmeTags',
            'degrees',
            'specialties',
            'verified',
            'accessedTour',
            'subscriptionStatus',
            'created',
        )
        read_only_fields = fields

class UserList(generics.ListAPIView):
    queryset = Profile.objects.all().order_by('-created')
    serializer_class = ReadProfileListSerializer
    permission_classes = (permissions.IsAdminUser, TokenHasReadWriteScope)

class UserDetail(generics.RetrieveAPIView):
    queryset = Profile.objects.all()
    serializer_class = ReadProfileDetailSerializer
    permission_classes = (permissions.IsAdminUser, TokenHasReadWriteScope)

class ReadOfferSerializer(serializers.ModelSerializer):
    userId = serializers.IntegerField(source='user.id')
    cmeTags = serializers.StringRelatedField(many=True)

    class Meta:
        model = BrowserCmeOffer
        fields = (
            'id',
            'userId',
            'activityDate',
            'url',
            'suggestedDescr',
            'cmeTags'
        )
        read_only_fields = fields


class UserOfferList(generics.ListAPIView):
    serializer_class = ReadOfferSerializer
    permission_classes = (permissions.IsAdminUser, TokenHasReadWriteScope)

    def get_queryset(self):
        userid = self.kwargs['pk']
        now = timezone.now()
        return BrowserCmeOffer.objects.filter(
            user=userid,
            expireDate__gt=now,
            redeemed=False
            ).order_by('-modified')


# intended to be used by SerializerMethodField on ReadFeedSerializer
class BRCmeSubSerializer(serializers.ModelSerializer):
    offer = serializers.PrimaryKeyRelatedField(read_only=True) # must specifiy read_only despite also putting it read_only_fields

    class Meta:
        model = BrowserCme
        fields = (
            'offer',
            'credits',
            'url',
            'purpose',
            'planEffect'
        )
        read_only_fields = fields

class SRCmeSubSerializer(serializers.ModelSerializer):
    class Meta:
        model = SRCme
        fields = ('credits',)
        read_only_fields = fields

class NotificationSubSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('expireDate',)
        read_only_fields = fields

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


class ReadFeedSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id')
    entryType = serializers.StringRelatedField()
    tags = serializers.StringRelatedField(many=True)
    creditType = serializers.ReadOnlyField(source='formatCreditType')
    extra = serializers.SerializerMethodField()
    numDocuments = serializers.IntegerField(source='getNumDocuments')

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
            'activityDate',
            'description',
            'tags',
            'numDocuments',
            'creditType',
            'extra',
            'created',
            'modified'
        )
        read_only_fields = fields


class UserFeedList(generics.ListAPIView):
    serializer_class = ReadFeedSerializer
    permission_classes = (permissions.IsAdminUser, TokenHasReadWriteScope)

    def get_queryset(self):
        userid = self.kwargs['pk']
        return Entry.objects.filter(user=userid, valid=True).order_by('-created')
