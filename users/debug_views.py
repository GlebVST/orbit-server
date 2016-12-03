from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.http import QueryDict
from django.utils import timezone
from rest_framework import generics, permissions, status
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
            points=Decimal('10.0'),
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
            pointsEarned = Decimal('1.0')
            rewardEntry = Reward.objects.create(
                entry=entry,
                rewardType='TEST-REWARD',
                points=pointsEarned
            )
            PointTransaction.objects.create(
                customer=customer,
                points=pointsEarned,
                pricePaid=Decimal('0'),
                transactionId=newUuid()
            )
            customer.balance += pointsEarned
            customer.save()
        context = {
            'success': True,
            'id': entry.pk,
            'balance': customer.balance
        }
        return Response(context, status=status.HTTP_201_CREATED)

