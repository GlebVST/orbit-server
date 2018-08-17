import logging
from django.conf import settings
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone

from rest_framework import generics, exceptions, permissions, status, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope
# proj
from common.logutils import *
# app
from .models import *
from .feed_serializers import *
from .permissions import *

logger = logging.getLogger('api.feed')

class LogValidationErrorMixin(object):
    def handle_exception(self, exc):
        response = super(LogValidationErrorMixin, self).handle_exception(exc)
        if response is not None and isinstance(exc, exceptions.ValidationError):
            #logWarning(logger, self.request, exc.get_full_details())
            message = "ValidationError: {0}".format(exc.detail)
            #logError(logger, self.request, message)
            logWarning(logger, self.request, message)
        return response


# EntryType - list only
class EntryTypeList(generics.ListAPIView):
    queryset = EntryType.objects.all().order_by('name')
    serializer_class = EntryTypeSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# Sponsor - list only
class SponsorList(generics.ListAPIView):
    queryset = Sponsor.objects.all().order_by('name')
    serializer_class = SponsorSerializer
    permission_classes = [IsAdminOrAuthenticated, TokenHasReadWriteScope]

# custom pagination for OrbitCmeOfferList
class OrbitCmeOfferPagination(PageNumberPagination):
    page_size = 5

class OrbitCmeOfferList(generics.ListAPIView):
    """
    Get the un-redeemed and unexpired valid offers order by modified desc
    (latest modified first) for the authenticated user.
    """
    serializer_class = OrbitCmeOfferSerializer
    pagination_class = OrbitCmeOfferPagination
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanViewOffer)

    def get_queryset(self):
        user = self.request.user
        now = timezone.now()
        filter_kwargs = dict(
            valid=True,
            user=user,
            expireDate__gt=now,
            redeemed=False)
        return OrbitCmeOffer.objects.filter(**filter_kwargs).select_related('sponsor','url').order_by('-modified')


class FeedListPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000

class FeedList(generics.ListAPIView):
    serializer_class = EntryReadSerializer
    pagination_class = FeedListPagination
    permission_classes = (CanViewFeed, permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        return Entry.objects.filter(user=user, valid=True).select_related('entryType','sponsor').order_by('-created')


class FeedEntryDetail(LogValidationErrorMixin, generics.RetrieveDestroyAPIView):
    serializer_class = EntryReadSerializer
    permission_classes = (CanViewFeed, IsOwnerOrAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        return Entry.objects.filter(user=user, valid=True).select_related('entryType', 'sponsor')

    def perform_destroy(self, instance):
        """Entry must be of type srcme else raise ValidationError"""
        if instance.entryType != ENTRYTYPE_SRCME:
            raise serializers.ValidationError('Invalid entryType for deletion.')

    def delete(self, request, *args, **kwargs):
        """Delete entry and any documents associated with it.
        Currently, only SRCme entries can be deleted from the UI.
        """
        instance = self.get_object()
        if instance.documents.exists():
            for doc in instance.documents.all():
                logDebug(logger, request, 'Deleting document {0}'.format(doc))
                doc.delete()
        return self.destroy(request, *args, **kwargs)


class InvalidateEntry(generics.UpdateAPIView):
    serializer_class = EntryReadSerializer
    permission_classes = (CanInvalidateEntry, IsOwnerOrAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        return Entry.objects.filter(user=user, valid=True)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        msg = 'Invalidate entry {0}'.format(instance)
        logInfo(logger, request, msg)
        instance.valid = False
        instance.save()
        context = {'success': True}
        return Response(context)


class InvalidateOffer(generics.UpdateAPIView):
    serializer_class = OrbitCmeOfferSerializer
    permission_classes = (IsOwnerOrAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        return OrbitCmeOffer.objects.filter(user=user, valid=True)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.redeemed:
            context = {
                'success': False,
                'message': 'Offer has already been redeemed.'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        msg = 'Invalidate offer {0.pk}/{0}'.format(instance)
        logInfo(logger, request, msg)
        instance.valid = False
        instance.save()
        context = {'success': True}
        return Response(context)


class TagsMixin(object):
    """Mixin to handle the tags parameter in request.data
    for SRCme and BrowserCme entry form.
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

class CreateBrowserCme(LogValidationErrorMixin, TagsMixin, generics.CreateAPIView):
    """
    Create a BrowserCme Entry in the user's feed.
    This action redeems the offer specified in the request.
    """
    serializer_class = BRCmeCreateSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanPostBRCme)

    def perform_create(self, serializer, format=None):
        user = self.request.user
        with transaction.atomic():
            # Create entry, brcme instances and redeem offer
            brcme = serializer.save(user=user)
        return brcme

    def create(self, request, *args, **kwargs):
        """Override create to add custom keys to response"""
        form_data = request.data.copy()
        self.get_tags(form_data)
        serializer = self.get_serializer(data=form_data)
        serializer.is_valid(raise_exception=True)
        brcme = self.perform_create(serializer)
        entry = brcme.entry
        user = request.user
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        pdata = UserSubscription.objects.serialize_permissions(user, user_subs)
        context = {
            'success': True,
            'id': entry.pk,
            'logo_url': entry.sponsor.logo_url,
            'created': entry.created,
            'brcme': model_to_dict(brcme),
            'permissions': pdata['permissions'],
            'brcme_limit': pdata['brcme_limit']
        }
        return Response(context, status=status.HTTP_201_CREATED)


class UpdateBrowserCme(LogValidationErrorMixin, TagsMixin, generics.UpdateAPIView):
    """
    Update a BrowserCme Entry in the user's feed.
    This action does not change the credits earned from the original creation.
    """
    serializer_class = BRCmeUpdateSerializer
    permission_classes = (IsEntryOwner, TokenHasReadWriteScope)

    def get_queryset(self):
        return BrowserCme.objects.select_related('entry')

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        form_data = request.data.copy()
        self.get_tags(form_data)
        serializer = self.get_serializer(instance, data=form_data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        entry = Entry.objects.get(pk=instance.pk)
        context = {
            'success': True,
            'modified': entry.modified
        }
        return Response(context)



class CreateSRCme(LogValidationErrorMixin, TagsMixin, generics.CreateAPIView):
    """
    Create SRCme Entry in the user's feed.
    """
    serializer_class = SRCmeFormSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, CanPostSRCme)

    def get_queryset(self):
        user = self.request.user
        return SRCme.objects.filter(user=user).select_related('entry')

    def perform_create(self, serializer, format=None):
        """
        If documents is specified, verify that document.user
            is request.user, else raise ValidationError.
        """
        user = self.request.user
        doc_ids = self.request.data.get('documents', [])
        for doc_id in doc_ids:
            qset = Document.objects.filter(pk=doc_id)
            if qset.exists():
                doc = qset[0]
                if doc.user != user:
                    error_msg = 'CreateSRCme: The documentId {0} is not owned by user: {1}.'.format(doc_id, user)
                    logWarning(logger, self.request, error_msg)
                    raise serializers.ValidationError(error_msg)
            else:
                error_msg = 'CreateSRCme: Invalid documentId {0} - does not exist.'.format(doc_id)
                logWarning(logger, self.request, error_msg)
                raise serializers.ValidationError(error_msg)
        # validate creditType (enable code after ui changes)
        #creditType = self.request.data.get('creditType', '')
        #if creditType != Entry.CREDIT_CATEGORY_1 or creditType != Entry.CREDIT_OTHER:
        #    raise serializers.ValidationError('Invalid creditType.')
        with transaction.atomic():
            srcme = serializer.save(user=user)
        return srcme

    def create(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        form_data = request.data.copy()
        #pprint(form_data)
        self.get_tags(form_data)
        in_serializer = self.get_serializer(data=form_data)
        in_serializer.is_valid(raise_exception=True)
        srcme = self.perform_create(in_serializer)
        out_serializer = CreateSRCmeOutSerializer(srcme.entry)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


class UpdateSRCme(LogValidationErrorMixin, TagsMixin, generics.UpdateAPIView):
    """
    Update an existing SRCme Entry in the user's feed.
    """
    serializer_class = SRCmeFormSerializer
    permission_classes = (IsEntryOwner, TokenHasReadWriteScope)

    def get_queryset(self):
        return SRCme.objects.select_related('entry')

    def perform_update(self, serializer, format=None):
        """If documents is specified, verify that document.user
        is request.user, else raise ValidationError.
        """
        user = self.request.user
        # check documents
        doc_ids = self.request.data.get('documents', [])
        for doc_id in doc_ids:
            qset = Document.objects.filter(pk=doc_id)
            if qset.exists():
                doc = qset[0]
                if doc.user != user:
                    error_msg = 'UpdateSRCme: The documentId {0} is not owned by user: {1}.'.format(doc_id, user)
                    logWarning(logger, self.request, error_msg)
                    raise serializers.ValidationError(error_msg)
            else:
                error_msg = 'UpdateSRCme: Invalid documentId {0} - does not exist.'.format(doc_id)
                logWarning(logger, self.request, error_msg)
                raise serializers.ValidationError(error_msg)
        with transaction.atomic():
            srcme = serializer.save(user=user)
        return srcme

    def update(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        form_data = request.data.copy()
        self.get_tags(form_data)
        in_serializer = self.get_serializer(instance, data=form_data, partial=partial)
        in_serializer.is_valid(raise_exception=True)
        self.perform_update(in_serializer)
        entry = Entry.objects.get(pk=instance.pk)
        out_serializer = UpdateSRCmeOutSerializer(entry)
        return Response(out_serializer.data)


class StoryDetail(APIView):
    """Finds the latest non-expired Story and returns the info with the launch_url customized for the user.
    Value is None if none exists.
    """
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def serialize_and_render(self, user_id, story):
        context = {'story': None}
        if story:
            s = StorySerializer(story)
            context['story'] = s.data
            context['story']['launch_url'] += "={0}".format(user_id)
        return Response(context, status=status.HTTP_200_OK)

    def get(self, request, format=None):
        story = None
        user_id = request.user.profile.getAuth0Id()
        now = timezone.now()
        qset = Story.objects.filter(startDate__lte=now, endDate__gt=now).order_by('-created')
        if qset.exists():
            story = qset[0]
        return self.serialize_and_render(user_id, story)

