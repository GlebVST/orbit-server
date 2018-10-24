import calendar
import coreapi
from datetime import datetime, timedelta
from hashids import Hashids
import logging
from operator import itemgetter
from smtplib import SMTPException
import pytz
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMessage
from django.db import transaction
from django.forms.models import model_to_dict
from django.template.loader import get_template
from django.utils import timezone

from rest_framework import generics, exceptions, permissions, status, serializers
from rest_framework.filters import BaseFilterBackend
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope
# proj
from common.logutils import *
from common.signals import profile_saved
# app
from .auth0_tools import Auth0Api
from .models import *
from .enterprise_serializers import *
from .serializers import ProfileReadSerializer, UserSubsReadSerializer
from .upload_serializers import UploadOrgFileSerializer
from .permissions import *
from .emailutils import makeSubject

logger = logging.getLogger('api.entpv')

class LogValidationErrorMixin(object):
    def handle_exception(self, exc):
        response = super(LogValidationErrorMixin, self).handle_exception(exc)
        if response is not None and isinstance(exc, exceptions.ValidationError):
            #logWarning(logger, self.request, exc.get_full_details())
            message = "ValidationError: {0}".format(exc.detail)
            #logError(logger, self.request, message)
            logWarning(logger, self.request, message)
        return response


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
        filter_kwargs = {
            'organization': org,
            'removeDate__isnull': True,
            'pending': False
        }
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
            orderByFields = ['created', 'user__profile__lastName', 'user__profile__firstName']
        elif o == 'compliance':
            orderByFields = ['compliance', 'user__profile__lastName', 'user__profile__firstName']
        elif o == 'verified':
            orderByFields = ['user__profile__verified', 'user__profile__lastName', 'user__profile__firstName']
        if otype == 'd':
            orderByFields[0] = '-' + orderByFields[0]
        if search_term:
            return OrgMember.objects.search_filter(search_term, filter_kwargs, orderByFields)
        # no search_term:
        return queryset.filter(**filter_kwargs).order_by(*orderByFields)


class OrgMemberListPagination(PageNumberPagination):
    page_size = 500
    page_size_query_param = 'page_size'
    max_page_size = 1000

class OrgMemberList(generics.ListCreateAPIView):
    queryset = OrgMember.objects.filter(removeDate__isnull=True) # active only
    serializer_class = OrgMemberReadSerializer
    pagination_class = OrgMemberListPagination
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]
    filter_backends = (OrgMemberFilterBackend,)

    def get_serializer_class(self):
        """Note: django-rest-swagger call this without a request object so must check for request attr"""
        if hasattr(self, 'request') and self.request:
            if self.request.method.upper() == 'GET':
                return OrgMemberReadSerializer
        return OrgMemberFormSerializer

    def perform_create(self, serializer, format=None):
        """If email is given, check that it does not trample on an existing user account
            unless user account is an inactive OrgMember, then reactivate and return this instance
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
                    instance = org_qset[0]
                    user_subs = UserSubscription.objects.getLatestSubscription(instance.user)
                    if user_subs is None or user_subs.canRejoinEnterpise():
                        logInfo(logger, self.request, 'Re-activate membership for {0}'.format(u))
                        with transaction.atomic():
                            instance.removeDate = None
                            instance.save()
                            user_subs = UserSubscription.objects.activateEnterpriseSubscription(instance.user, org)
                            return instance
                    else:
                        # User has an active Individual/BT subscription. User must opt-in via JoinTeam email
                        error_msg = 'The user {0} must be transferred using join-team.'.format(email)
                        logWarning(logger, self.request, error_msg)
                        raise serializers.ValidationError({'email': error_msg}, code='invalid')
                else:
                    # User account already exists and user is not an existing orgmember.
                    # Cannot use this endpoint b/c this is intended to create a new user profile
                    error_msg = 'The email {0} belongs to another user account.'.format(email)
                    logWarning(logger, self.request, error_msg)
                    raise serializers.ValidationError({'email': error_msg}, code='invalid')
        apiConn = Auth0Api.getConnection(self.request)
        with transaction.atomic():
            instance = serializer.save(apiConn=apiConn, organization=org) # returns OrgMember instance
        logInfo(logger, self.request, 'Created OrgMember {0.pk}'.format(instance))
        return instance

    def create(self, request, *args, **kwargs):
        form_data = request.data.copy()
        serializer = self.get_serializer(data=form_data)
        serializer.is_valid(raise_exception=True)
        instance = self.perform_create(serializer)
        out_serializer = OrgMemberReadSerializer(instance)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


class OrgMemberDetail(generics.RetrieveUpdateAPIView):
    serializer_class = OrgMemberFormSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]

    def get_serializer_class(self):
        """Note: django-rest-swagger call this without a request object so must check for request attr"""
        if hasattr(self, 'request') and self.request:
            if self.request.method.upper() == 'GET':
                return OrgMemberReadSerializer
        return OrgMemberFormSerializer

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
                error_msg = u'The email {0} belongs to another user account.'.format(email)
                logWarning(logger, self.request, error_msg)
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
        logInfo(logger, request, 'Updated OrgMember {0.pk}'.format(instance))
        m = OrgMember.objects.get(pk=instance.pk)
        out_serializer = OrgMemberReadSerializer(m)
        return Response(out_serializer.data)

class UploadRoster(LogValidationErrorMixin, generics.CreateAPIView):
    serializer_class = UploadOrgFileSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]
    parser_classes = (FormParser, MultiPartParser)

    def perform_create(self, serializer, format=None):
        """Create OrgFile instance and send EmailMessage to MANAGERS"""
        user = self.request.user
        org = user.profile.organization
        instance = serializer.save(user=user, organization=org)
        try:
            fileData = instance.document.read()
        except Exception, e:
            logger.error('UploadRoster readFile Exception: {0}'.format(e))
            raise serializers.ValidationError('readFile Exception')
        else:
            # create EmailMessage
            from_email = settings.EMAIL_FROM
            to_email = [t[1] for t in settings.MANAGERS] # list of emails
            subject = makeSubject('New Roster File Upload from {0.code}'.format(org))
            ctx = {
                'user': user,
                'orgfile': instance
            }
            message = get_template('email/upload_roster_notification.html').render(ctx)
            msg = EmailMessage(
                    subject,
                    message,
                    to=to_email,
                    from_email=from_email)
            msg.content_subtype = 'html'
            msg.attach(instance.name, fileData, instance.content_type)
            try:
                msg.send()
            except SMTPException as e:
                logException(logger, self.request, 'UploadRoster send email failed.')
        return instance

    def create(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        in_serializer = self.get_serializer(data=request.data)
        in_serializer.is_valid(raise_exception=True)
        instance = self.perform_create(in_serializer)
        out_serializer = OrgFileReadSerializer(instance)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


class EmailSetPassword(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]

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
                logError(logger, request, 'EmailSetPassword failed for user {0}. ticket_url={1}'.format(user, ticket_url))
                return Response({'success': False}, status=status.HTTP_400_BAD_REQUEST)
            else:
                context = {'success': True}
                return Response(context, status=status.HTTP_200_OK)
        return Response({'success': False}, status=status.HTTP_404_NOT_FOUND)


class TeamStats(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]
    def get(self, request, start, end):
        try:
            startdt = datetime.utcfromtimestamp(int(start))
            enddt = datetime.utcfromtimestamp(int(end))
        except ValueError:
            context = {
                'error': 'Invalid date parameters'
            }
            message = context['error'] + ': ' + start + ' - ' + end
            logWarning(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        org = user.profile.organization
        totalCreditsStartDate = org.creditStartDate.date().isoformat()
        filter_kwargs = {
                'organization': org,
                'day__gte': startdt.date(),
                'day__lte': enddt.date()
            }
        qset = OrbitCmeOfferAgg.objects.filter(**filter_kwargs).order_by('day')
        s = OrbitCmeOfferAggSerializer(qset, many=True)
        # convert org.providerStat to list
        providerStat = org.providerStat # dict abbrev => {count, lastCount, diff}
        providers = []
        for abbrev in providerStat:
            d = providerStat[abbrev]
            providers.append({
                'title': abbrev,
                'count': d['count'],
                'diff': d['diff']
                })
        providers.sort(key=itemgetter('count'), reverse=True)
        context = {
            'organization': org.name,
            'totalCredits': float(org.credits),
            'totalCreditsStartDate': totalCreditsStartDate,
            'providers': providers,
            'articlesRead': s.data
        }
        return Response(context, status=status.HTTP_200_OK)

#
# This endpoint is called when an invited existing user clicks the link in their JoinTeam email.
# The user should have been invited via the sendJoinTeamEmail managemment cmd.
# Steps:
# 1. Check OrgMember instance for request.user and pending=True.
#  If removeDate is not None: clear it (re-activate membership)
# 2. Terminate current user_subs and begin new Enterprise subs
# 3. Emit profile_saved signal (to create usergoals)
class JoinTeam(APIView):
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def post(self, request, *args, **kwargs):
        user = self.request.user
        qset = OrgMember.objects.filter(user=user, pending=True).order_by('-modified')
        if not qset.exists():
            logger.warning('No pending OrgMember instance found')
            error_msg = 'Invalid or expired invitation'
            raise serializers.ValidationError({'user': error_msg}, code='invalid')
        m = qset[0] # pending OrgMember instance
        with transaction.atomic():
            m.pending = False
            if m.removeDate is not None:
                m.removeDate = None
            m.save(update_fields=('pending', 'removeDate',))
            logInfo(logger, self.request, 'JoinTeam for OrgMember {0}'.format(m))
            # transfer user to Enterprise subscription
            user_subs = UserSubscription.objects.activateEnterpriseSubscription(user, org)
            # emit profile_saved signal
            ret = profile_saved.send(sender=user.profile.__class__, user_id=user.pk)
        # prepare context
        profile = Profile.objects.get(pk=user.pk)
        if not user_subs:
            user_subs = UserSubscription.objects.getLatestSubscription(user)
        pdata = UserSubscription.objects.serialize_permissions(user, user_subs)
        context = {
            'success': True,
            'profile': ProfileReadSerializer(profile).data,
            'subscription': UserSubsReadSerializer(user_subs).data,
            'permissions': pdata['permissions'],
            'brcme_limit': pdata['brcme_limit']
        }
        return Response(context, status=status.HTTP_200_OK)
