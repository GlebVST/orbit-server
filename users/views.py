from decimal import Decimal
import json
from pprint import pprint
from django.contrib.auth.models import User
from django.db import transaction
from django.http import QueryDict
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser,MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.ext.rest_framework import TokenHasReadWriteScope, TokenHasScope
from common.viewutils import  newUuid
# app
from .models import *
from .serializers import *
from .permissions import *

# Degree
class DegreeList(generics.ListCreateAPIView):
    queryset = Degree.objects.all().order_by('abbrev')
    serializer_class = DegreeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class DegreeDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Degree.objects.all()
    serializer_class = DegreeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# PracticeSpecialty
class PracticeSpecialtyList(generics.ListCreateAPIView):
    queryset = PracticeSpecialty.objects.all().order_by('name')
    serializer_class = PracticeSpecialtySerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class PracticeSpecialtyDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = PracticeSpecialty.objects.all()
    serializer_class = PracticeSpecialtySerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# CmeTag
class CmeTagList(generics.ListCreateAPIView):
    queryset = CmeTag.objects.all().order_by('name')
    serializer_class = CmeTagSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class CmeTagDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = CmeTag.objects.all()
    serializer_class = CmeTagSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# EntryType
class EntryTypeList(generics.ListCreateAPIView):
    queryset = EntryType.objects.all().order_by('name')
    serializer_class = EntryTypeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class EntryTypeDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = EntryType.objects.all()
    serializer_class = EntryTypeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]


# Profile
# A list of profiles is readable by any authenticated user
# A profile cannot be created from the API because it is created by the psa pipeline for each user.
class ProfileList(generics.ListAPIView):
    queryset = Profile.objects.all().order_by('lastName')
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

# A profile is viewable by any authenticated user.
# A profile can edited only by the owner from the API
# A profile cannot be deleted from the API
class ProfileDetail(generics.RetrieveUpdateAPIView):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = [IsOwnerOrAuthenticated, TokenHasReadWriteScope]


# Customer
# A list of customers is readable by any Admin user
# A customer cannot be created from the API because it is created by the psa pipeline for each user.
class CustomerList(generics.ListAPIView):
    queryset = Customer.objects.all().order_by('-created')
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAdminUser, TokenHasReadWriteScope]

# A customer is viewable by any Admin user.
# A customer can edited only by the owner from the API
# A customer cannot be deleted from the API
class CustomerDetail(generics.RetrieveUpdateAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsOwnerOrAdmin, TokenHasReadWriteScope]


# PointPurchaseOption
class PPOList(generics.ListCreateAPIView):
    queryset = PointPurchaseOption.objects.all().order_by('points')
    serializer_class = PPOSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class PPODetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = PointPurchaseOption.objects.all()
    serializer_class = PPOSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# PointRewardOption
class PROList(generics.ListCreateAPIView):
    queryset = PointRewardOption.objects.all().order_by('points')
    serializer_class = PROSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class PRODetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = PointRewardOption.objects.all()
    serializer_class = PROSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]


# BrowserCmeOffer
class GetBrowserCmeOffer(APIView):
    """
    Find the first un-redeemed and unexpired offer with the earliest
    expireDate for the authenticated user.
    If no offer exists, returns {offer: null}
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def serialize_and_render(self, offer):
        context = {'offer': None}
        if offer:
            s_offer = BrowserCmeOfferSerializer(offer)
            context['offer'] = s_offer.data
        return Response(context, status=status.HTTP_200_OK)

    def get(self, request, format=None):
        now = timezone.now()
        qset = BrowserCmeOffer.objects.filter(
            user=request.user,
            expireDate__gt=now,
            redeemed=False
            ).order_by('expireDate')
        if qset.exists():
            offer = qset[0]
        else:
            offer = None
        return self.serialize_and_render(offer)

#
# FEED
#
class FeedList(generics.ListAPIView):
    serializer_class = EntryReadSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

    def get_queryset(self):
        user = self.request.user
        return Entry.objects.filter(user=user, valid=True).select_related('entryType').order_by('-created')

class FeedEntryDetail(generics.RetrieveDestroyAPIView):
    serializer_class = EntryReadSerializer
    permission_classes = [IsOwnerOrAuthenticated, TokenHasReadWriteScope]

    def get_queryset(self):
        user = self.request.user
        return Entry.objects.filter(user=user, valid=True).select_related('entryType')

    def delete(self, request, *args, **kwargs):
        """Override to delete associated document if one exists"""
        instance = self.get_object()
        if instance.document:
            instance.document.delete()
        return self.destroy(request, *args, **kwargs)


class CreateBrowserCme(generics.CreateAPIView):
    """
    Create a BrowserCme Entry in the user's feed.
    This action redeems the BrowserCmeOffer specified in the
    request, and deducts points from the customer's balance.
    """
    serializer_class = BRCmeCreateSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

    def perform_create(self, serializer, format=None):
        user = self.request.user
        with transaction.atomic():
            brcme = serializer.save(user=user)
            offer = brcme.offer
            # set redeemed flag on offer
            offer.redeemed = True
            offer.save()
            # create PointTransaction
            pointsDeducted = -1*offer.points
            PointTransaction.objects.create(
                customer=self.customer,
                points=pointsDeducted,
                pricePaid=Decimal('0'),
                transactionId=newUuid()
            )
            # deduct points from user's balance
            self.customer.balance += pointsDeducted
            self.customer.save()
        return brcme

    def create(self, request, *args, **kwargs):
        """Override create to add custom keys to response"""
        # get local customer instance for request.user
        try:
            self.customer = Customer.objects.get(user=request.user)
        except ObjectDoesNotExist:
            context = {
                'success': False,
                'error': 'Local customer object not found for user'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        brcme = self.perform_create(serializer)
        entry = brcme.entry
        offer = brcme.offer
        context = {
            'success': True,
            'id': entry.pk,
            'created': entry.created,
            'credits': offer.credits,
            'balance': self.customer.balance
        }
        return Response(context, status=status.HTTP_201_CREATED)


class UpdateBrowserCme(generics.UpdateAPIView):
    """
    Update a BrowserCme Entry in the user's feed.
    This action does not change the credits earned or the points
    deducted from the original creation.
    """
    serializer_class = BRCmeUpdateSerializer
    permission_classes = [IsEntryOwner, TokenHasReadWriteScope]

    def get_queryset(self):
        return BrowserCme.objects.select_related('entry')

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        entry = Entry.objects.get(pk=instance.pk)
        context = {
            'success': True,
            'modified': entry.modified
        }
        return Response(context)

# http://stackoverflow.com/questions/30176570/using-django-rest-framework-how-can-i-upload-a-file-and-send-a-json-payload
class CreateSRCmeSpec(generics.CreateAPIView):
    """Alternate version of create SRCme.
    This version conforms to the original API specification. But it does not
    work Swagger becuase it expects this input format:
        entry : JSON.stringify({
            activityDate: str  (required) future date is allowed
            description: str   (required) 500 chars max
            credits: float     (required, must be positive number)
            tags: array of tag Ids (at least 1 id is required)
            fileMd5: str       (optional. Value is the md5sum of the document to upload)
        })
        file: blob (optional. document to upload. Max filesize=X MB)
    """
    serializer_class = SRCmeFormSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    parser_classes = (MultiPartParser,FormParser,)

    def get_queryset(self):
        user = self.request.user
        return SRCme.objects.filter(user=user).select_related('entry')

    def perform_create(self, serializer, format=None):
        user = self.request.user
        with transaction.atomic():
            srcme = serializer.save(user=user)
        return srcme

    def create(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        print(request.data)
        try:
            form_data = json.loads(request.data['entry'])
            if request.data.get('document'):
                form_data['document'] = request.data['document']
        except ValueError, e:
            context = {
                'success': False,
                'error': 'Malformed JSON for entry key'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            serializer = self.get_serializer(data=form_data)
            serializer.is_valid(raise_exception=True)
            srcme = self.perform_create(serializer)
            entry = srcme.entry
            if entry.document is not None:
                documentUrl = entry.document.url
            else:
                documentUrl = None
            context = {
                'success': True,
                'id': entry.pk,
                'created': entry.created,
                'documentUrl': documentUrl
            }
            headers = self.get_success_headers(serializer.data)
            return Response(context, status=status.HTTP_201_CREATED, headers=headers)


class CreateSRCme(generics.CreateAPIView):
    """
    Create SRCme Entry in the user's feed.
    This version works in Swagger UI.
    File upload is optional. If file is given, then client
    must also provide file md5.
    """
    serializer_class = SRCmeFormSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    parser_classes = (MultiPartParser,FormParser,)

    def get_queryset(self):
        user = self.request.user
        return SRCme.objects.filter(user=user).select_related('entry')

    def perform_create(self, serializer, format=None):
        user = self.request.user
        with transaction.atomic():
            srcme = serializer.save(user=user)
        return srcme

    def create(self, request, *args, **kwargs):
        """Override to add custom keys to response"""
        print(request.data)  # a QueryDict
        form_data = request.data.copy()
        # Change tags to be a list of pks
        tags = form_data.get('tags', '')
        if tags:
            qdict = QueryDict(tags)
            tag_ids = qdict.getlist('tags')
            form_data.setlist('tags', tag_ids)
        print(form_data)
        serializer = self.get_serializer(data=form_data)
        serializer.is_valid(raise_exception=True)
        srcme = self.perform_create(serializer)
        entry = srcme.entry
        context = {
            'success': True,
            'id': entry.pk,
            'created': entry.created
        }
        return Response(context, status=status.HTTP_201_CREATED)

class UpdateSRCme(generics.UpdateAPIView):
    """
    Update an existing SRCme Entry in the user's feed. This
    version works in Swagger UI.
    """
    serializer_class = SRCmeFormSerializer
    permission_classes = [IsEntryOwner, TokenHasReadWriteScope]
    parser_classes = (MultiPartParser,FormParser,)

    def get_queryset(self):
        return SRCme.objects.select_related('entry')

    def update(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        #print(request.data)
        form_data = request.data.copy()
        # Change tags to be a list of pks
        tags = form_data.get('tags', '')
        if tags:
            qdict = QueryDict(tags)
            tag_ids = qdict.getlist('tags')
            form_data.setlist('tags', tag_ids)
        serializer = self.get_serializer(instance, data=form_data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        entry = Entry.objects.get(pk=instance.pk)
        context = {
            'success': True,
            'modified': entry.modified
        }
        return Response(context)


class UpdateSRCmeSpec(generics.UpdateAPIView):
    """Alternate version that conforms to original spec but does not work in Swagger.
    Update an existing SRCme Entry in the user's feed.
    """
    serializer_class = SRCmeFormSerializer
    permission_classes = [IsEntryOwner, TokenHasReadWriteScope]
    parser_classes = (MultiPartParser,FormParser,)

    def get_queryset(self):
        return SRCme.objects.select_related('entry')

    def update(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        print(request.data)
        try:
            form_data = json.loads(request.data['entry'])
            if request.data.get('document'):
                form_data['document'] = request.data['document']
        except ValueError, e:
            context = {
                'success': False,
                'error': 'Malformed JSON for entry key'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            serializer = self.get_serializer(instance, data=form_data, partial=partial)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            entry = Entry.objects.get(pk=instance.pk)
            context = {
                'success': False,
                'modified': entry.modified
            }
            return Response(context)


# User Feedback
class UserFeedbackList(generics.ListCreateAPIView):
    serializer_class = UserFeedbackSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def get_queryset(self):
        return UserFeedback.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
