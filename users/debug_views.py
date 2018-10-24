import logging
import coreapi
from datetime import date, datetime, timedelta
from decimal import Decimal
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
from rest_framework.filters import BaseFilterBackend
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope
# app
from .auth0_tools import Auth0Api
from .emailutils import sendCancelReminderEmail, sendRenewalReminderEmail, sendCardExpiredAlertEmail
from .models import *
from .permissions import *
from .serializers import *
from .enterprise_serializers import *

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
    serializer_class = InvitationDiscountReadSerializer
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


class OrgMemberFilterBackend(BaseFilterBackend):
    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name='q',
                location='query',
                required=False,
                type='string',
                description='Search by firstName, lastName or email'
                ),
            coreapi.Field(
                name='compliance',
                location='query',
                required=False,
                type='string',
                description='Filter by compliance: [0-4]'
                ),
            coreapi.Field(
                name='verified',
                location='query',
                required=False,
                type='string',
                description='Filter by verified: 0 or 1'
                ),
            coreapi.Field(
                name='o',
                location='query',
                required=False,
                type='string',
                description='Order By one of: lastname/created/compliance/verified'
                ),
            coreapi.Field(
                name='otype',
                location='query',
                required=False,
                type='string',
                description='a for ASC. d for DESC'
                ),
            ]

    def filter_queryset(self, request, queryset, view):
        """This requires the model Manager to have a search_filter manager method"""
        org = request.user.profile.organization
        search_term = request.query_params.get('q', '').strip()
        compliance = None
        verified = None
        q_compliance = request.query_params.get('compliance', '').strip()
        try:
            compliance = int(q_compliance)
        except ValueError:
            compliance = None
        q_verified = request.query_params.get('verified', '').strip()
        try:
            verified = bool(int(q_verified))
        except ValueError:
            verified = None
        # basic filter kwargs
        filter_kwargs = {'organization': org, 'removeDate__isnull': True, 'pending': False}
        if compliance is not None:
            filter_kwargs['compliance'] = compliance
        if verified is not None:
            filter_kwargs['user__profile__verified'] = verified
        o = request.query_params.get('o', 'lastname').strip()
        otype = request.query_params.get('otype', 'a').strip() # sort primary field by ASC/DESC
        # set orderByFields from o
        if o == 'lastname':
            orderByFields = ['user__profile__lastName', 'user__profile__firstName', 'created']
        elif o == 'created':
            orderByFields = ['created', 'fullname']
        elif o == 'compliance':
            orderByFields = ['compliance', 'fullname']
        elif o == 'verified':
            orderByFields = ['user__profile__verified', 'fullname']
        if otype == 'd':
            orderByFields[0] = '-' + orderByFields[0]
        if search_term:
            return OrgMember.objects.search_filter(search_term, filter_kwargs, orderByFields)
        return queryset.filter(**filter_kwargs).order_by(*orderByFields)


class OrgMemberList(generics.ListAPIView):
    queryset = OrgMember.objects.filter(removeDate__isnull=True)
    serializer_class = OrgMemberReadSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]
    filter_backends = (OrgMemberFilterBackend,)


class CreateOrgMember(generics.CreateAPIView):
    serializer_class = OrgMemberFormSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]

    def perform_create(self, serializer, format=None):
        """If email is given, check that it does not trample on an existing user account
        Save auth0 token info to request.session
        """
        org = self.request.user.profile.organization
        # check email
        email = self.request.data.get('email', '')
        if email:
            qset = User.objects.filter(email__iexact=email)
            if qset.exists():
                u = qset[0]
                org_qset = OrgMember.objects.filter(organization=org, user=u, removeDate__isnull=False)
                if org_qset.exists():
                    print('CreateOrgMember: re-activate existing membership for {0}'.format(u))
                    instance = org_qset[0]
                    instance.removeDate = None
                    instance.save()
                    return instance
                error_msg = 'This email already belongs to another user account.'
                raise serializers.ValidationError({'email': error_msg}, code='invalid')
        apiConn = Auth0Api.getConnection(self.request)
        with transaction.atomic():
            instance = serializer.save(apiConn=apiConn, organization=org)
        return instance

    def create(self, request, *args, **kwargs):
        form_data = request.data.copy()
        serializer = self.get_serializer(data=form_data)
        serializer.is_valid(raise_exception=True)
        instance = self.perform_create(serializer)
        out_serializer = OrgMemberReadSerializer(instance)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)

class OrgMemberDetail(generics.RetrieveAPIView):
    serializer_class = OrgMemberReadSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]


    def get_queryset(self):
        """This ensures that an OrgMember instance can only be retrieved by
        an admin belonging to the same org as the member
        """
        org = self.request.user.profile.organization
        return OrgMember.objects.filter(organization=org)


class UpdateOrgMember(generics.UpdateAPIView):
    serializer_class = OrgMemberFormSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]


    def get_queryset(self):
        """This ensures that an OrgMember instance can only be updated by
        an admin belonging to the same org as the member
        """
        org = self.request.user.profile.organization
        return OrgMember.objects.filter(organization=org)

    def perform_update(self, serializer, format=None):
        """If email is given, check that it does not trample on an existing user account"""
        # check email
        m = self.get_object()
        email = self.request.data.get('email', '')
        if email and m.user.email != email:
            qset = User.objects.filter(email__iexact=email).exclude(pk=m.user.pk)
            if qset.exists():
                error_msg = 'The email {0} belongs to another user account.'.format(email)
                raise serializers.ValidationError({'email': error_msg}, code='invalid')
        apiConn = Auth0Api.getConnection(self.request)
        with transaction.atomic():
            instance = serializer.save(apiConn=apiConn)
        return instance

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        form_data = request.data.copy()
        in_serializer = self.get_serializer(instance, data=form_data, partial=partial)
        in_serializer.is_valid(raise_exception=True)
        self.perform_update(in_serializer)
        m = OrgMember.objects.get(pk=instance.pk)
        out_serializer = OrgMemberReadSerializer(m)
        return Response(out_serializer.data)


class EmailSetPassword(APIView):
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

    def post(self, request, *args, **kwargs):
        memberid = self.kwargs.get('pk')
        if memberid:
            qset = OrgMember.objects.filter(pk=memberid)
            if not qset.exists():
                return Response({'success': False}, status=status.HTTP_404_NOT_FOUND)
            orgmember = qset[0]
            user = orgmember.user
            profile = user.profile
            apiConn = Auth0Api.getConnection(self.request)
            ticket_url = apiConn.change_password_ticket(profile.socialId, UI_LOGIN_URL)
            try:
                delivered = sendPasswordTicketEmail(orgmember, ticket_url)
                if delivered:
                    orgmember.setPasswordEmailSent = True
                    orgmember.save(update_fields=('setPasswordEmailSent',))
            except SMTPException as e:
                logError('EmailSetPassword failed for user {0}. ticket_url={1}'.format(user, ticket_url))
                return Response({'success': False}, status=status.HTTP_400_BAD_REQUEST)
            else:
                context = {'success': True}
                return Response(context, status=status.HTTP_200_OK)
        return Response({'success': False}, status=status.HTTP_404_NOT_FOUND)
