from datetime import datetime
from decimal import Decimal
from pprint import pprint
import pytz
from django.contrib.auth.models import User
from django.db import transaction
from django.http import QueryDict
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser,MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.ext.rest_framework import TokenHasReadWriteScope, TokenHasScope
from common.viewutils import  newUuid
# app
from .models import *
from .serializers import *
from .permissions import *


# Country
class CountryList(generics.ListCreateAPIView):
    queryset = Country.objects.all().order_by('id')
    serializer_class = CountrySerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class CountryDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# Degree
class DegreeList(generics.ListCreateAPIView):
    queryset = Degree.objects.all().order_by('id')
    serializer_class = DegreeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class DegreeDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Degree.objects.all()
    serializer_class = DegreeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# PracticeSpecialty
# custom pagination for large page size
class LongPagination(PageNumberPagination):
    page_size = 10000

class PracticeSpecialtyList(generics.ListCreateAPIView):
    queryset = PracticeSpecialty.objects.all().order_by('name')
    serializer_class = PracticeSpecialtySerializer
    pagination_class = LongPagination
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class PracticeSpecialtyDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = PracticeSpecialty.objects.all()
    serializer_class = PracticeSpecialtySerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# CmeTag
class CmeTagList(generics.ListCreateAPIView):
    queryset = CmeTag.objects.all().order_by('-priority', 'name')
    serializer_class = CmeTagSerializer
    pagination_class = LongPagination
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
    queryset = Profile.objects.all().order_by('lastName').select_related('country')
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

# A profile is viewable by any authenticated user.
# A profile can edited only by the owner from the API
# A profile cannot be deleted from the API
class ProfileDetail(generics.RetrieveUpdateAPIView):
    queryset = Profile.objects.all().select_related('country')
    serializer_class = ProfileSerializer
    permission_classes = [IsOwnerOrAuthenticated, TokenHasReadWriteScope]


# Customer
# A list of customers is readable by any Admin user
# A customer cannot be created from the API because it is created by the psa pipeline for each user.
class CustomerList(generics.ListAPIView):
    queryset = Customer.objects.all().order_by('-created')
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAdminUser, TokenHasReadWriteScope]

# A customer is viewable by any Admin user (or the user that is the owner of the account)
# A customer cannot be edited from the API because it only contains read-only fields
# A customer cannot be deleted from the API
class CustomerDetail(generics.RetrieveAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsOwnerOrAdmin, TokenHasReadWriteScope]

# SubscriptionPlan : new payment model
class SubscriptionPlanList(generics.ListCreateAPIView):
    queryset = SubscriptionPlan.objects.all().order_by('created')
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

class SubscriptionPlanDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]


# custom pagination for BrowserCmeOfferList
class BrowserCmeOfferPagination(PageNumberPagination):
    page_size = 5

class BrowserCmeOfferList(generics.ListAPIView):
    """
    Find the top N un-redeemed and unexpired offers order by expireDate
    (earliest first) for the authenticated user.
    """
    serializer_class = BrowserCmeOfferSerializer
    pagination_class = BrowserCmeOfferPagination
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

    def get_queryset(self):
        user = self.request.user
        now = timezone.now()
        return BrowserCmeOffer.objects.filter(
            user=user,
            expireDate__gt=now,
            redeemed=False
            ).order_by('expireDate')

class GetBrowserCmeOffer(APIView):
    """
    Find the earliest un-redeemed and unexpired offers order by expireDate
    for the authenticated user.
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
class FeedListPagination(PageNumberPagination):
    page_size = 100

class FeedList(generics.ListAPIView):
    serializer_class = EntryReadSerializer
    pagination_class = FeedListPagination
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

    def get_queryset(self):
        user = self.request.user
        return Entry.objects.filter(user=user, valid=True).select_related('entryType').order_by('-activityDate')

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

class TagsMixin(object):
    """Mixin to handle the tags parameter in request.data
    for BrowserCme.
    """

    def get_tags(self, form_data):
        """Handle different format for tags in request body
        Swagger UI sends tags as a list, e.g.
            tags: ['1','2']
        UI sends tags as a comma separated string of IDs, e.g.
            tags: "1,2"
        """
        #pprint(form_data) # <type 'dict'>
        tags = form_data.get('tags', '')
        if type(tags) == type(u'') and ',' in tags:
            tag_ids = tags.split(",") # convert "1,2" to [1,2]
            form_data['tags'] = tag_ids

class CreateBrowserCme(TagsMixin, generics.CreateAPIView):
    """
    Create a BrowserCme Entry in the user's feed.
    This action redeems the BrowserCmeOffer specified in the
    request, and sets the redeemed flag on the offer.
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
        form_data = request.data.copy()
        self.get_tags(form_data)
        logger.debug(form_data)
        serializer = self.get_serializer(data=form_data)
        serializer.is_valid(raise_exception=True)
        brcme = self.perform_create(serializer)
        entry = brcme.entry
        offer = brcme.offer
        context = {
            'success': True,
            'id': entry.pk,
            'created': entry.created,
            'credits': offer.credits
        }
        return Response(context, status=status.HTTP_201_CREATED)


class UpdateBrowserCme(TagsMixin, generics.UpdateAPIView):
    """
    Update a BrowserCme Entry in the user's feed.
    This action does not change the credits earned from the original creation.
    """
    serializer_class = BRCmeUpdateSerializer
    permission_classes = [IsEntryOwner, TokenHasReadWriteScope]

    def get_queryset(self):
        return BrowserCme.objects.select_related('entry')

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        form_data = request.data.copy()
        self.get_tags(form_data)
        logger.debug(form_data)
        serializer = self.get_serializer(instance, data=form_data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        entry = Entry.objects.get(pk=instance.pk)
        context = {
            'success': True,
            'modified': entry.modified
        }
        return Response(context)


class SRCmeTagsMixin(object):
    """Mixin to handle the tags parameter in request.data"""

    def get_tags(self, form_data):
        """Handle different format for tags in request body
        UI sends tags as a comma separated string of IDs
        Swagger UI sends tags in the select multiple format,
            e.g. tags=1&tags2
        """
        tags = form_data.get('tags', '')
        if tags:
            if ',' in tags:  # comma separated list of pks
                tag_ids = tags.split(",") # [1,2]
            else:
                # format sent by swagger
                qdict = QueryDict(tags) # tags=1&tags=2
                tag_ids = qdict.getlist('tags') # [1,2]
            form_data.setlist('tags', tag_ids)


class CreateSRCme(SRCmeTagsMixin, generics.CreateAPIView):
    """
    Create SRCme Entry in the user's feed.
    File upload is optional. If file is given, then client
    must also provide the md5sum of the file.
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
        form_data = request.data.copy() # a QueryDict
        self.get_tags(form_data)
        logger.debug(form_data)
        in_serializer = self.get_serializer(data=form_data)
        in_serializer.is_valid(raise_exception=True)
        srcme = self.perform_create(in_serializer)
        out_serializer = CreateSRCmeOutSerializer(srcme.entry)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)

class UpdateSRCme(SRCmeTagsMixin, generics.UpdateAPIView):
    """
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
        form_data = request.data.copy()
        self.get_tags(form_data)
        logger.debug(form_data)
        in_serializer = self.get_serializer(instance, data=form_data, partial=partial)
        in_serializer.is_valid(raise_exception=True)
        self.perform_update(in_serializer)
        entry = Entry.objects.get(pk=instance.pk)
        out_serializer = UpdateSRCmeOutSerializer(entry)
        return Response(out_serializer.data)



# User Feedback
class UserFeedbackList(generics.ListCreateAPIView):
    serializer_class = UserFeedbackSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def get_queryset(self):
        return UserFeedback.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

#
# Dashboard
#
class CmeAggregateStats(APIView):
    """
    This view expects a start date and end date in UNIX epoch format
    (number of seconds since 1970/1/1) as URL parameters. It calculates
    the total SRCme and BrowserCme for the time period for the current
    user, and also the total by tag.
    
    parameters:
        - name: start
          description: seconds since epoch
          required: true
          type: string
          paramType: form
        - name: end
          description: seconds since epoch
          required: true
          type: string
          paramType: form
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def serialize_and_render(self, stats):
        context = {
            'result': stats
        }
        return Response(context, status=status.HTTP_200_OK)

    def get(self, request, start, end):
        try:
            startdt = timezone.make_aware(datetime.datetime.utcfromtimestamp(int(start)), pytz.utc)
            enddt = timezone.make_aware(datetime.datetime.utcfromtimestamp(int(end)), pytz.utc)
        except ValueError:
            context = {
                'error': 'Invalid date parameters'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        try:
            profile = Profile.objects.get(user=request.user)
        except Profile.DoesNotExist:
            context = {
                'error': 'Invalid user. No profile found.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        user_tags = profile.cmeTags.all()
        satag = CmeTag.objects.get(name=CMETAG_SACME)
        stats = {
            ENTRYTYPE_BRCME: {
                'total': Entry.objects.sumBrowserCme(request.user, startdt, enddt)
            },
            ENTRYTYPE_SRCME: {
                'total': Entry.objects.sumSRCme(request.user, startdt, enddt),
                satag.name: Entry.objects.sumSRCme(request.user, startdt, enddt, satag)
            }
        }
        for tag in user_tags:
            stats[ENTRYTYPE_BRCME][tag.name] = Entry.objects.sumBrowserCme(request.user, startdt, enddt, tag)
            stats[ENTRYTYPE_SRCME][tag.name] = Entry.objects.sumSRCme(request.user, startdt, enddt, tag)
        return self.serialize_and_render(stats)
