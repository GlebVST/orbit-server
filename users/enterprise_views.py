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
from time import sleep
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
from .serializers import ProfileReadSerializer, ProfileUpdateSerializer, UserSubsReadSerializer
from .upload_serializers import UploadOrgFileSerializer
from .permissions import *
from .emailutils import makeSubject, sendJoinTeamEmail
from .dashboard_views import AuditReportMixin
from goals.serializers import UserLicenseGoalSummarySerializer
from goals.models import UserGoal

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


# OrgGroup (Enterprise Practice Divisions)
class OrgGroupList(LogValidationErrorMixin, generics.ListCreateAPIView):
    serializer_class = OrgGroupSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]

    def get_queryset(self):
        """Return only the groups belonging to the same Org as the request.user"""
        return OrgGroup.objects.filter(organization=self.request.user.profile.organization).order_by('name')

    def perform_create(self, serializer):
        req_user = self.request.user # OrgMember user with is_admin=True
        org = req_user.profile.organization
        if not org:
            error_msg = 'Admin user is not assigned to any organization.'
            raise serializers.ValidationError({'name': error_msg}, code='invalid')
            return
        instance = serializer.save(organization=org)
        return instance

class OrgGroupDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]
    queryset = OrgGroup.objects.all()
    serializer_class = OrgGroupSerializer

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
                name='group',
                location='query',
                required=False,
                type='string',
                description='Filter by groupId'
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
        q_group = request.query_params.get('group', '').strip()
        try:
            groupId = int(q_group)
        except ValueError:
            groupId = None
        # basic filter kwargs
        filter_kwargs = {
            'organization': org,
        }
        if compliance is not None:
            filter_kwargs['compliance'] = compliance
        if verified is not None:
            filter_kwargs['user__profile__verified'] = verified
        if groupId is not None:
            filter_kwargs['group'] = groupId
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

class OrgMemberList(generics.ListAPIView):
    queryset = OrgMember.objects.all()
    serializer_class = OrgMemberReadSerializer
    pagination_class = OrgMemberListPagination
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]

    def get_queryset(self):
        orderByFields = ['user__profile__lastName', 'user__profile__firstName', 'created']
        return OrgMember.objects \
            .select_related('organization','group','user__profile') \
            .filter(organization=self.request.user.profile.organization) \
            .order_by(*orderByFields)

class OrgMemberCreate(generics.CreateAPIView):
    queryset = OrgMember.objects.all()
    serializer_class = OrgMemberFormSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]

    def perform_create(self, serializer, format=None):
        """If user account for email already exists:
            call sendJoinTeamEmail to send invitation email to user
        else:
            Proceed with form and create new user account.
            Save auth0 token info to request.session
        Returns: OrgMember instance/None if no email in form_data
        """
        req_user = self.request.user # EnterpriseAdmin user
        org = req_user.profile.organization
        if not org:
            error_msg = 'Admin user is not assigned to any organization.'
            raise serializers.ValidationError({'email': error_msg}, code='invalid')
            return
        try:
            plan = SubscriptionPlan.objects.getEnterprisePlanForOrg(org)
        except IndexError:
            error_msg = "Failed to find SubscriptionPlan for Organization of admin user: {0.name}".format(org)
            raise serializers.ValidationError({'email': error_msg}, code='invalid')
            return
        # check group
        orggroup = None
        groupid = self.request.data.get('group', None)
        if groupid:
            # verify that group.org = req_user's org
            try:
                orggroup = OrgGroup.objects.get(pk=groupid)
            except OrgGroup.DoesNotExist:
                error_msg = 'Invalid group id - does not exist.'
                raise serializers.ValidationError({'group': error_msg}, code='invalid')
                return
            else:
                if orggroup.organization != org:
                    error_msg = 'Invalid group id for this org.'
                    raise serializers.ValidationError({'group': error_msg}, code='invalid')
                    return
        # check email
        email = self.request.data.get('email', '')
        if not email:
            return
        user_qset = User.objects.filter(email__iexact=email)
        if user_qset.exists():
            user = user_qset[0]
            # User account already exists, so need to send joinTeam invitation email
            # Is user already a pending member of org
            org_qset = OrgMember.objects.filter(organization=org, user=user).order_by('-created')
            if org_qset.exists():
                instance = org_qset[0]
                if instance.pending:
                    logInfo(logger, self.request, 'User is already pending OrgMember {0.pk}'.format(instance))
                elif instance.removeDate is not None:
                    logInfo(logger, self.request, 'User {0} is removed OrgMember {1.pk}. Set pending to True'.format(user, instance))
                    instance.pending = True
                    instance.save(update_fields=('pending',))
                else:
                    error_msg = 'The user {0} already belongs to the team.'.format(user)
                    logWarning(logger, self.request, error_msg)
                    raise serializers.ValidationError({'email': error_msg}, code='invalid')
            else:
                # create pending OrgMember
                instance = OrgMember.objects.createMember(org, orggroup, user.profile, pending=True)
                logInfo(logger, self.request, 'Created pending OrgMember {0}'.format(instance))
            # send JoinTeam email
            try:
                msg = sendJoinTeamEmail(user, org, send_message=True)
            except SMTPException, e:
                logException(logger, self.request, 'sendJoinTeamEmail failed to pending OrgMember {0.id}.'.format(instance))
        else:
            # create new user account and send password ticket email
            apiConn = Auth0Api.getConnection(self.request)
            with transaction.atomic():
                instance = serializer.save(apiConn=apiConn, organization=org, plan=plan) # returns OrgMember instance
                profile = instance.user.profile
                profileUpdateSerializer = ProfileUpdateSerializer(profile, data=self.request.data)
                profileUpdateSerializer.is_valid(raise_exception=True)
                profile = profileUpdateSerializer.save()
                # emit profile_saved signal for non admin users
                if profile.allowUserGoals() and not instance.is_admin:
                    ret = profile_saved.send(sender=profile.__class__, user_id=instance.user.pk)
            logInfo(logger, self.request, 'Created OrgMember {0.pk}'.format(instance))
        return instance

    def create(self, request, *args, **kwargs):
        form_data = request.data.copy()
        serializer = self.get_serializer(data=form_data)
        serializer.is_valid(raise_exception=True)
        instance = self.perform_create(serializer)
        out_serializer = OrgMemberDetailSerializer(instance)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


class OrgMembersRemove(APIView):
    """This view sets `removeDate` field on all OrgMember instances matching passed ids array
    Example JSON in the DELETE data:
        {"ids": [1, 23, 94]}
    """
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]
    def post(self, request, *args, **kwargs):
        ids = request.data.get('ids', [])
        logInfo(logger, self.request, 'Remove OrgMembers: {}'.format(ids))
        updates = []
        now = timezone.now()
        members = OrgMember.objects.select_related('user__profile').filter(pk__in=ids)
        for member in members:
            member.removeDate = now
            member.save(update_fields=('removeDate',))
            updates.append({
                "id": member.id,
                "removeDate": member.removeDate
            })
            # if wasn't enterprise user (like existing orbit user hasn't accepted org invite) -
            # below method won't do anything
            UserSubscription.objects.endEnterpriseSubscription(member.user)
        context = {'success': True, 'data':updates}
        return Response(context, status=status.HTTP_200_OK)

class OrgMemberDetail(generics.RetrieveAPIView):
    serializer_class = OrgMemberDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]

    def get_queryset(self):
        """This ensures that an OrgMember instance can only be updated by
        an admin belonging to the same org as the member
        """
        org = self.request.user.profile.organization
        return OrgMember.objects.select_related('organization','group','user__profile').filter(organization=org)

class OrgMemberLicenseList(generics.ListAPIView):
    serializer_class = UserLicenseGoalSummarySerializer
    permission_classes = (permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope)

    def list(self, request, *args, **kwargs):
        try:
            member = OrgMember.objects.get(pk=self.kwargs['pk'])
        except OrgMember.DoesNotExist:
            return Response([], status=status.HTTP_404_NOT_FOUND)

        queryset = UserGoal.objects.getLicenseGoalsForUserSummary(member.user)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class OrgMemberUpdate(generics.UpdateAPIView):
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
                error_msg = u'The email {0} belongs to another user account.'.format(email)
                logWarning(logger, self.request, error_msg)
                raise serializers.ValidationError({'email': error_msg}, code='invalid')
        apiConn = Auth0Api.getConnection(self.request)
        with transaction.atomic():
            instance = serializer.save(apiConn=apiConn)
            profile = instance.user.profile
            profileUpdateSerializer = ProfileUpdateSerializer(profile, data=self.request.data, partial=self.partial)
            profileUpdateSerializer.is_valid(raise_exception=True)
            profile = profileUpdateSerializer.save()
            # emit profile_saved signal for non admin users
            if profile.allowUserGoals() and not instance.is_admin:
                ret = profile_saved.send(sender=profile.__class__, user_id=instance.user.pk)
        return instance

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        self.partial = partial
        instance = self.get_object()
        form_data = request.data.copy()
        in_serializer = self.get_serializer(instance, data=form_data, partial=partial)
        in_serializer.is_valid(raise_exception=True)
        self.perform_update(in_serializer)
        logInfo(logger, request, 'Updated OrgMember {0.pk}'.format(instance))
        m = OrgMember.objects.get(pk=instance.pk)
        out_serializer = OrgMemberDetailSerializer(m)
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
            logError(logger, self.request, 'UploadRoster readFile Exception: {0}'.format(e))
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


class OrgMembersEmailInvite(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]

    def post(self, request, *args, **kwargs):
        ids = request.data.get('ids', [])
        logInfo(logger, self.request, 'Repeat email invites for OrgMembers: {}'.format(ids))
        apiConn = Auth0Api.getConnection(self.request)
        members = OrgMember.objects.select_related('user__profile').filter(pk__in=ids)
        for member in members:
            if member.pending:
                # member get into a pending state only when existing Orbit user get invited to organisation
                # so for such users we send a join-team email
                try:
                    sendJoinTeamEmail(member.user, member.organization, send_message=True)
                    # add small delay here to prevent potential spamming alerts?
                    sleep(0.2)
                except SMTPException, e:
                    logException(logger, self.request, 'sendJoinTeamEmail failed to pending OrgMember {0.fullname}.'.format(member))
                else:
                    member.inviteDate = timezone.now()
                    member.save(update_fields=('inviteDate',))
            elif not member.user.profile.verified:
                # unverified users with non-pending state are those recently invited and never actually joined Orbit
                # so for such users we send a set-password email
                OrgMember.objects.sendPasswordTicket(member.user.profile.socialId, member, apiConn)
                # auth0 rate-limit API calls on a free tier to 2 requests per second
                # https://auth0.com/docs/policies/rate-limits
                sleep(0.5)
        context = {'success': True}
        return Response(context, status=status.HTTP_200_OK)

class OrgMembersRestore(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope]

    def post(self, request, *args, **kwargs):
        ids = request.data.get('ids', [])
        logInfo(logger, self.request, 'Restore email invites for OrgMembers: {}'.format(ids))
        updates = []
        now = timezone.now()
        members = OrgMember.objects.select_related('user', 'organization').filter(pk__in=ids, removeDate__isnull=False)
        for member in members:
            # restore removed member
            member.removeDate = None
            member.pending = True
            member.inviteDate = now
            member.save(update_fields=('pending', 'removeDate','inviteDate'))
            updates.append({
                "id": member.id,
                "inviteDate": member.inviteDate,
                "pending": True,
                "joined": False,
                "removeDate": None,
            })
            # since member was removed they should have been moved to a free trial subscription
            # so ask them to join organisation
            try:
                sendJoinTeamEmail(member.user, member.organization, send_message=True)
            except SMTPException, e:
                logException(logger, self.request, 'sendJoinTeamEmail failed to pending OrgMember {0.fullname}.'.format(member))
        context = {'success': True, 'data': updates}
        return Response(context, status=status.HTTP_200_OK)


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
            logWarning(logger, self.request, 'No pending OrgMember instance found')
            error_msg = 'Invalid or expired invitation'
            raise serializers.ValidationError({'user': error_msg}, code='invalid')
        m = qset[0] # pending OrgMember instance
        org = m.organization
        profile = Profile.objects.get(pk=user.pk)
        # get specific Enterprise plan to use from org.
        try:
            plan = SubscriptionPlan.objects.getEnterprisePlanForOrg(org)
        except IndexError:
            error_msg = "Failed to find SubscriptionPlan for OrgMember organization: {0.name}".format(org)
            raise serializers.ValidationError({'user': error_msg}, code='invalid')
            return
        with transaction.atomic():
            m.pending = False
            if m.removeDate is not None:
                m.removeDate = None
            m.save(update_fields=('pending', 'removeDate',))
            logInfo(logger, self.request, 'JoinTeam for OrgMember {0}'.format(m))

            # make sure profile email is marked as verified once user join by the email link
            # (say someone had unverified email when being independent user)
            if not profile.verified:
                profile.verified = True
                profile.save(update_fields=('verified',))
                # update Auth0 record to have the same email_verified state
                apiConn = Auth0Api.getConnection(self.request)
                apiConn.setEmailVerified(profile.socialId)

            # transfer user to Enterprise subscription
            user_subs = UserSubscription.objects.activateEnterpriseSubscription(user, m.organization, plan)
            # emit profile_saved signal
            if profile.allowUserGoals() and not m.is_admin:
                ret = profile_saved.send(sender=user.profile.__class__, user_id=user.pk)

        # prepare context
        if not user_subs:
            user_subs = UserSubscription.objects.getLatestSubscription(user)
        pdata = UserSubscription.objects.serialize_permissions(user, user_subs)
        context = {
            'success': True,
            'profile': ProfileReadSerializer(profile).data,
            'subscription': UserSubsReadSerializer(user_subs).data,
            'permissions': pdata['permissions'],
            'credits': pdata['credits']
        }
        return Response(context, status=status.HTTP_200_OK)

class EnterpriseMemberAuditReport(AuditReportMixin, APIView):
    """
    This view expects a userid plus start date and end date in UNIX epoch format
    (number of seconds since 1970/1/1) as URL parameters.
    It generates an Audit Report for the date range, and uploads to S3.
    If user has earned browserCme credits in the date range, it also
    generates a Certificate that is associated with the report.

    parameters:
        - name: userid
          description: target user ID to generate report for
          required: true
          type: string
          paramType: form
        - name: start
          description: seconds since epoch
          required: true
          type: string
          paramType: form
        - name: end
          description: seconds since epoch
          required: true
          type: string
          paramType: form
    """
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope, IsEnterpriseAdmin)
    def post(self, request, memberId, start, end):
        # check if specified user is member if the same organisation as admin
        admin_user = request.user
        admin_org = admin_user.profile.organization
        qset = OrgMember.objects.filter(organization=admin_org, id=memberId)
        if not qset.exists():
            logWarning(logger, self.request, 'Admin user {0} tried to generate audit report for org member {1}, not existing in their organisation: {2}'.format(admin_user.id, memberId, admin_org.id))
            return Response({'results': [], 'error': 'Failed to generate audit report: no member found'}, status=status.HTTP_404_NOT_FOUND)
        target_user = qset[0].user
        try:
            startdt = timezone.make_aware(datetime.utcfromtimestamp(int(start)), pytz.utc)
            enddt = timezone.make_aware(datetime.utcfromtimestamp(int(end)), pytz.utc)
            if startdt >= enddt:
                context = {
                    'error': 'Start date must be prior to End Date.'
                }
                return Response(context, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            context = {
                'error': 'Invalid date parameters'
            }
            message = context['error'] + ': ' + start + ' - ' + end
            logWarning(logger, request, message)
            return Response(context, status=status.HTTP_400_BAD_REQUEST)

        return self.generateUserReport(target_user, startdt, enddt, request)
