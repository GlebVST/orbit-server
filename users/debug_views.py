from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
import premailer
from io import StringIO
from smtplib import SMTPException
from django.contrib.auth.models import User
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.template.loader import get_template
from django.utils import timezone
import pytz
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser,MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope
# app
from .models import *
from .permissions import *
from .serializers import *
from .emailutils import sendCancelReminderEmail, sendRenewalReminderEmail, sendCardExpiredAlertEmail

class MakeOrbitCmeOffer(APIView):
    """
    Create a test OrbitCmeOffer for the authenticated user.
    Pick a random AllowedUrl for the url for the offer.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        now = timezone.now()
        activityDate = now - timedelta(seconds=10)
        expireDate = datetime(now.year+1, 1,1, tzinfo=pytz.utc)
        esiteids = EligibleSite.objects.getSiteIdsForProfile(user.profile)
        # exclude urls for which user already has un-redeemed un-expired offers waiting to be redeemed
        exclude_urls = OrbitCmeOffer.objects.filter(
            user=user,
            redeemed=False,
            eligible_site__in=esiteids,
            expireDate__gte=now
        ).values_list('url', flat=True).distinct()
        #print('Num exclude_urls: {0}'.format(len(exclude_urls)))
        aurl = AllowedUrl.objects.filter(eligible_site__in=esiteids).exclude(pk__in=exclude_urls).order_by('?')[0]
        esite = aurl.eligible_site
        specnames = [p.name for p in esite.specialties.all()]
        #print(specnames)
        spectags = CmeTag.objects.filter(name__in=specnames)
        with transaction.atomic():
            offer = OrbitCmeOffer.objects.create(
                user=user,
                eligible_site=esite,
                url=aurl,
                activityDate=activityDate,
                expireDate=expireDate,
                suggestedDescr=aurl.page_title,
                credits=Decimal('0.5'),
                sponsor_id=1
            )
            offer.tags.set(list(spectags))
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


class MakeStoryCme(APIView):
    """
    Create a test StoryCme entry for the user using the latest Story (if dne), else return the existing StoryCme.
    The entry will be tagged with SA-CME.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        story = Story.objects.all().order_by('-created')[0]
        #user = User.objects.get(pk=3)
        user = request.user
        qset = StoryCme.objects.filter(story=story, entry__user=user)
        if qset.exists():
            m = qset[0]
            context = {
                'success': True,
                'id': m.entry.pk,
            }
            return Response(context, status=status.HTTP_200_OK)
        # else
        now = timezone.now()
        satag = CmeTag.objects.get(name=CMETAG_SACME)
        activityDate = now - timedelta(seconds=5)
        entryType = EntryType.objects.get(name=ENTRYTYPE_STORY_CME)
        creditType = Entry.CREDIT_CATEGORY_1
        with transaction.atomic():
            entry = Entry.objects.create(
                user=user,
                entryType=entryType,
                activityDate=activityDate,
                ama_pra_catg=creditType,
                sponsor=story.sponsor,
                description='Created for feed test'
            )
            StoryCme.objects.create(
                entry=entry,
                story=story,
                credits=story.credits,
                url=story.entry_url,
                title=story.entry_title
            )
            entry.tags.add(satag)
        context = {
            'success': True,
            'id': entry.pk,
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
        message = get_template('email/receipt.html').render(ctx)
        msg = EmailMessage(subject, message, to=[user.email], from_email=from_email)
        msg.content_subtype = 'html'
        try:
            msg.send()
        except SMTPException as e:
            logException(logger, request, 'EmailSubscriptionReceipt send email failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
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
        message = get_template('email/payment_failed.html').render(ctx)
        msg = EmailMessage(subject, message, to=[user.email], from_email=from_email)
        msg.content_subtype = 'html'
        try:
            msg.send()
        except SMTPException as e:
            logException(logger, request, 'EmailSubscriptionPaymentFailure send email failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context = {
                'success': True,
                'message': 'A payment failure notice was emailed to {0.email}'.format(user),
                'transactionId': subs_trans.transactionId
            }
            return Response(context, status=status.HTTP_200_OK)


class InvitationDiscountList(generics.ListAPIView):
    """List of InvitationDiscounts for the current authenticated user as inviter"""
    serializer_class = ReadInvitationDiscountSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        return InvitationDiscount.objects.filter(inviter=user).select_related().order_by('-created')

class PreEmail(APIView):
    """send test email using premailer
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        etype = EntryType.objects.get(name=ENTRYTYPE_BRCME)
        now = timezone.now()
        cutoff = now - timedelta(days=90)
        entries = Entry.objects.filter(
                user=user,
                entryType=etype,
                valid=True,
                created__gte=cutoff).order_by('-created')
        data = []
        for m in entries:
            data.append(dict(
                id=m.pk,
                url=m.brcme.url,
                created=m.created
            ))
        from_email = settings.SUPPORT_EMAIL
        subject = 'Your Orbit monthly update'
        ctx = {
            'profile': user.profile,
            'entries': data,
            'reportDate': now
        }
        # setup premailer
        plog = StringIO()
        phandler = logging.StreamHandler(plog)
        orig_message = get_template('email/test_inline.html').render(ctx)
        p = premailer.Premailer(orig_message,
                cssutils_logging_handler=phandler,
                cssutils_logging_level=logging.INFO)
        # transformed message
        message = p.transform()
        print(plog.getvalue())
        msg = EmailMessage(subject, message, to=[user.email], from_email=from_email)
        msg.content_subtype = 'html'
        try:
            msg.send()
        except SMTPException as e:
            logException(logger, request, 'SendTestPreEmail failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context = {
                'success': True,
                'message': 'A message was emailed to {0.email}'.format(user),
            }
            return Response(context, status=status.HTTP_200_OK)


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
            title='Test PinnedMessage title',
            description='This is the description',
            sponsor_id=1,
            launch_url='https://docs.google.com/'
        )
        context = {
            'success': True,
            'id': message.pk,
        }
        return Response(context, status=status.HTTP_201_CREATED)


class EmailCardExpired(APIView):
    """Call emailutils.SendCardExpiredAlertEmail for request.user
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        paymentMethods = Customer.objects.getPaymentMethods(user.customer)
        pm = paymentMethods[0]
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        try:
            sendCardExpiredAlertEmail(user_subs, pm)
        except SMTPException as e:
            logException(logger, request, 'EmailCardExpired failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context = {
                'success': True,
                'message': 'A message was emailed to {0.email}'.format(user),
                'paymentMethod': pm
            }
            return Response(context, status=status.HTTP_200_OK)

class EmailSubscriptionRenewalReminder(APIView):
    """Call emailutils.SendRenewalReminderEmail for request.user
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        paymentMethods = Customer.objects.getPaymentMethods(user.customer)
        pm = paymentMethods[0]
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        extra_data = {
            'totalCredits': int(BrowserCme.objects.totalCredits())
        }
        try:
            sendRenewalReminderEmail(user_subs, pm, extra_data)
        except SMTPException as e:
            logException(logger, request, 'EmailSubscriptionRenewalReminder failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context = {
                'success': True,
                'message': 'A message was emailed to {0.email}'.format(user),
                'paymentMethod': pm
            }
            return Response(context, status=status.HTTP_200_OK)


class EmailSubscriptionCancelReminder(APIView):
    """Call emailutils.SendCancelReminderEmail for request.user
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    def post(self, request, format=None):
        user = request.user
        paymentMethods = Customer.objects.getPaymentMethods(user.customer)
        pm = paymentMethods[0]
        user_subs = UserSubscription.objects.getLatestSubscription(user)
        extra_data = {
            'totalCredits': int(BrowserCme.objects.totalCredits())
        }
        try:
            sendCancelReminderEmail(user_subs, pm, extra_data)
        except SMTPException as e:
            logException(logger, request, 'EmailSubscriptionCancelReminder failed.')
            context = {'success': False, 'message': 'Failure sending email'}
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        else:
            context = {
                'success': True,
                'message': 'A message was emailed to {0.email}'.format(user),
            }
            return Response(context, status=status.HTTP_200_OK)
