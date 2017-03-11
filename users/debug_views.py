from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser,MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.ext.rest_framework import TokenHasReadWriteScope, TokenHasScope
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


class MakeNotification(APIView):
    """
    Create a test Notification Entry in the user's feed.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        # create reward entry for feed test
        now = timezone.now()
        activityDate = now - timedelta(seconds=10)
        expireDate = now + timedelta(days=10)
        entryType = EntryType.objects.get(name=ENTRYTYPE_NOTIFICATION)
        with transaction.atomic():
            entry = Entry.objects.create(
                user=request.user,
                entryType=entryType,
                activityDate=activityDate,
                description='Created for feed test'
            )
            Notification.objects.create(
                entry=entry,
                expireDate=expireDate,
            )
        context = {
            'success': True,
            'id': entry.pk,
        }
        return Response(context, status=status.HTTP_201_CREATED)

