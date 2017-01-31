from datetime import timedelta
import json
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.http import QueryDict
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser,MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.ext.rest_framework import TokenHasReadWriteScope, TokenHasScope
# proj
from common.viewutils import newUuid
# app
from .models import *
from .permissions import *
from .serializers import *

class MakeBrowserCmeOffer(APIView):
    """
    Create a test BrowserCmeOffer for the authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        now = timezone.now()
        activityDate = now - timedelta(days=1)
        expireDate = now + timedelta(days=1)
        url = 'https://radiopaedia.org/'
        pageTitle = 'Sample page title'
        offer = BrowserCmeOffer.objects.create(
            user=request.user,
            activityDate=activityDate,
            expireDate=expireDate,
            url=url,
            pageTitle=pageTitle,
            credits=Decimal('0.5')
        )
        context = {'success': True, 'id': offer.pk}
        return Response(context, status=status.HTTP_201_CREATED)


class MakeRewardEntry(APIView):
    """
    Create a test Reward Entry in the user's feed.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        # get local customer instance for request.user
        try:
            customer = Customer.objects.get(user=request.user)
        except ObjectDoesNotExist:
            context = {
                'success': False,
                'error': 'Local customer object not found for user'
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # create reward entry for feed test
        now = timezone.now()
        activityDate = now - timedelta(seconds=10)
        entryType = EntryType.objects.get(name=ENTRYTYPE_REWARD)
        with transaction.atomic():
            entry = Entry.objects.create(
                user=request.user,
                entryType=entryType,
                activityDate=activityDate,
                description='Created for feed test'
            )
            pointsEarned = Decimal('10.0')
            rewardEntry = Reward.objects.create(
                entry=entry,
                rewardType='TEST-REWARD',
                points=pointsEarned
            )
        context = {
            'success': True,
            'id': entry.pk,
        }
        return Response(context, status=status.HTTP_201_CREATED)

# Alternate versions of code
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


