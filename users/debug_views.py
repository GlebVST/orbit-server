from datetime import date, datetime, timedelta
from decimal import Decimal
from smtplib import SMTPException
from django.contrib.auth.models import User
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.template import Context
from django.template.loader import get_template
from django.utils import timezone
import pytz
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser,MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.ext.rest_framework import TokenHasReadWriteScope, TokenHasScope
# proj
from common.appconstants import PINNED_MESSAGE_TITLE_PREFIX
# app
from .models import *
from .permissions import *
from .serializers import *

class MakeBrowserCmeOffer(APIView):
    """
    Create a test BrowserCmeOffer for the authenticated user.
    Pick a random AllowedUrl for the url for the offer.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        now = timezone.now()
        activityDate = now - timedelta(seconds=10)
        expireDate = datetime(now.year+1, 1,1, tzinfo=pytz.utc)
        aurl = AllowedUrl.objects.all().order_by('?')[0]
        url = aurl.url
        pageTitle = 'Sample page title'
        suggestedDescr = 'This is the suggested description'
        offer = BrowserCmeOffer.objects.create(
            user=request.user,
            eligible_site=aurl.eligible_site,
            url=aurl.url,
            activityDate=activityDate,
            expireDate=expireDate,
            pageTitle=pageTitle,
            suggestedDescr=suggestedDescr,
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
This month we're exploring the application of machine learning
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
            title=PINNED_MESSAGE_TITLE_PREFIX + 'Artificial Intelligence in Healthcare',
            description=MESSAGE_DESCRIPTION,
            sponsor_id=1,
            launch_url='https://docs.google.com/'
        )
        context = {
            'success': True,
            'id': message.pk,
        }
        return Response(context, status=status.HTTP_201_CREATED)


class EmailSubscriptionReceipt(APIView):
    """
    Find the latest subscription transaction of the user
    and email a receipt for it, and return success:True and the transactionId.
    If no transaction exists: return success:False
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        #print('User: {0.pk} {0.email}'.format(user))
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        if not user_subs:
            context = {'success': False, 'message': 'User does not have a subscription.'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # does user_subs have associated payment transaction
        qset = user_subs.transactions.all().order_by('-created')
        if not qset.exists():
            context = {
                'success': False,
                'message': 'The UserSubscription {0.pk} does not have a payment transaction in the database yet.'.format(user_subs)
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # else prepare context for email
        subs_trans = qset[0]
        plan_name = u'Orbit ' + user_subs.plan.name
        subject = u'Your receipt for annual subscription to {0}'.format(plan_name)
        from_email = settings.SUPPORT_EMAIL
        ctx = {
            'profile': user.profile,
            'subscription': user_subs,
            'transaction': subs_trans,
            'plan_name': plan_name,
            'plan_monthly_price': user_subs.plan.monthlyPrice(),
            'support_email': settings.SUPPORT_EMAIL
        }
        message = get_template('email/receipt.html').render(Context(ctx))
        msg = EmailMessage(subject, message, to=[user.email], from_email=from_email)
        msg.content_subtype = 'html'
        try:
            msg.send()
        except SMTPException as e:
            logException(logger, request, 'EmailSubscriptionReceipt send email failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        finally:
            context = {
                'success': True,
                'message': 'A receipt was emailed to {0.email}'.format(user),
                'transactionId': subs_trans.transactionId
            }
            return Response(context, status=status.HTTP_200_OK)

class EmailSubscriptionPaymentFailure(APIView):
    """
    Find the latest subscription transaction of the user
    and send a payment failure email for it, and return success:True and the transactionId.
    If no transaction exists: return success:False
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        if not user_subs:
            context = {'success': False, 'message': 'User does not have a subscription.'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # does user_subs have associated payment transaction
        qset = user_subs.transactions.all().order_by('-created')
        if not qset.exists():
            context = {
                'success': False,
                'message': 'The UserSubscription {0.pk} does not have a payment transaction in the database yet.'.format(user_subs)
            }
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        # else prepare context for email
        subs_trans = qset[0]
        subject = u'Your Orbit Invoice Payment Failed [#{0.transactionId}]'.format(subs_trans)
        from_email = settings.SUPPORT_EMAIL
        username = None
        if user.profile.firstName:
            username = user.profile.firstName
        elif user.profile.npiFirstName:
            username = user.profile.npiFirstName
        else:
            username = user.email
        ctx = {
            'username': username,
            'transaction': subs_trans,
            'server_hostname': settings.SERVER_HOSTNAME,
            'support_email': settings.SUPPORT_EMAIL
        }
        message = get_template('email/payment_failed.html').render(Context(ctx))
        msg = EmailMessage(subject, message, to=[user.email], from_email=from_email)
        msg.content_subtype = 'html'
        try:
            msg.send()
        except SMTPException as e:
            logException(logger, request, 'EmailSubscriptionPaymentFailure send email failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        finally:
            context = {
                'success': True,
                'message': 'A payment failure notice was emailed to {0.email}'.format(user),
                'transactionId': subs_trans.transactionId
            }
            return Response(context, status=status.HTTP_200_OK)
