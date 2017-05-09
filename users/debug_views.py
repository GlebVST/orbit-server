from datetime import date, datetime, timedelta
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
            credits=Decimal('0.5'),
            sponsor_id=1
        )
        context = {'success': True, 'id': offer.pk}
        return Response(context, status=status.HTTP_201_CREATED)


class MakeNotification(APIView):
    """
    Create a test Notification Entry in the user's feed.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
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

MESSAGE_DESCRIPTION = """
This month in Expeditions, we're exploring the application of machine learning
to dermatology in work from the Berkeley Artificial Intelligence Research Lab.
Click [here][id_foo] for a related press release.


[id_foo]: http://bair.berkeley.edu/ "BAIR"
"""

class MakePinnedMessage(APIView):
    """
    Create a test PinnedMessage for the user.
    The description field may contain Markdown syntax.
    Reference: https://daringfireball.net/projects/markdown/syntax
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        now = timezone.now()
        startDate = datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)
        expireDate = now + timedelta(days=30)
        message = PinnedMessage.objects.create(
            user=request.user,
            startDate=startDate,
            expireDate=expireDate,
            title='Expeditions: Artificial Intelligence in Healthcare',
            description=MESSAGE_DESCRIPTION,
            sponsor_id=1
        )
        context = {
            'success': True,
            'id': message.pk,
        }
        return Response(context, status=status.HTTP_201_CREATED)

