from datetime import timedelta
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


NUM_ENTRIES = 50
class FeedList(APIView):
    """Manual attempt at feed list"""
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def make_entry_dict(self, entry):
        """entry common keys"""
        d = {
            'id': entry.pk,
            'entryType': entry.entryType.pk,
            'activityDate': entry.activityDate,
            'description': entry.description,
            'created': entry.created,
            'modified': entry.modified,
            'documentUrl': '',
            'extra': {}
        }
        if entry.document:
            d['documentUrl'] = entry.document.url
        return d

    def make_reward_dict(self, reward):
        """reward extra keys"""
        return {
            'rewardType': reward.rewardType,
            'points': reward.points
        }
    def make_brcme_dict(self, brcme):
        """browser-cme extra keys"""
        offer = brcme.offer
        purpose = 0 if brcme.isDiagnosis else 1
        planEffect = 0 if brcme.isPlanUnchanged else 1
        return {
            'credits': brcme.credits,
            'purpose': purpose,
            'planEffect': planEffect,
            'offer': offer.pk,
            'url': offer.url,
            'pageTitle': offer.pageTitle
        }
    def make_exbrcme_dict(self, exbrcme):
        """expired-browser-cme extra keys"""
        offer = exbrcme.offer
        return {
            'offer': offer.pk,
            'credits': offer.credits,
            'url': offer.url,
            'pageTitle': offer.pageTitle,
            'expireDate': offer.expireDate
        }
    def make_srcme_dict(self, srcme):
        """self-reported cme extra keys"""
        return {
            'credits': srcme.credits
        }

    def get(self, request, format=None):
        qset = Entry.objects.filter(user=request.user, valid=True).select_related('entryType').order_by('-created')
        paginator = Paginator(qset, NUM_ENTRIES, allow_empty_first_page=True)
        page = request.GET.get('page', 1)
        try:
            entries = paginator.page(page)
        except PageNotAnInteger:
            if paginator.num_pages:
                entries = paginator.page(1)
            else:
                entries = []
        except EmptyPage:
            if paginator.num_pages:
                entries = paginator.page(paginator.num_pages)
            else:
                entries = []
        data = []
        for entry in entries:
            entry_dict = self.make_entry_dict(entry)
            if entry.entryType.name == ENTRYTYPE_REWARD:
                extra = self.make_reward_dict(entry.reward)
            elif entry.entryType.name == ENTRYTYPE_BRCME:
                extra = self.make_brcme_dict(entry.brcme)
            elif entry.entryType.name == ENTRYTYPE_SRCME:
                extra = self.make_srcme_dict(entry.srcme)
            elif entry.entryType.name == ENTRYTYPE_EXBRCME:
                extra = self.make_exbrcme_dict(entry.exbrcme)
            else:
                extra = None
            if extra:
                entry_dict['extra'].update(extra)
            data.append(entry_dict)
        context = {
            'results': data,
            'page': page,
            'num_pages': paginator.num_pages
        }
        return Response(context, status=status.HTTP_200_OK)


