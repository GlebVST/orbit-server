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
from django.core.files.base import ContentFile
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
# app
from .auth0_tools import Auth0Api
from .models import *
from .enterprise_serializers import *
from .permissions import *

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
                name='o',
                location='query',
                required=False,
                type='string',
                description='order_by'
                ),
            ]

    def filter_queryset(self, request, queryset, view):
        """This requires the model Manager to have a search_filter manager method"""
        org = request.user.profile.organization
        search_term = request.query_params.get('q', '').strip()
        o = request.query_params.get('o', '').strip()
        # default order by
        orderByFields = ('user__profile__lastName', 'user__profile__firstName', 'created')
        if o == 'created':
            orderByFields = ('created', 'fullname')
        elif o == 'compliance':
            orderByFields = ('compliance', 'fullname')
        elif o == 'verified':
            orderByFields = ('user__profile__verified', 'fullname')

        if search_term:
            logInfo(logger, request, search_term)
            return OrgMember.objects.search_filter(org, search_term, orderByFields)
        # no search_term: filter by org
        return queryset.filter(organization=org).order_by(*orderByFields)

class OrgMemberList(generics.ListCreateAPIView):
    queryset = OrgMember.objects.filter(removeDate__isnull=True) # active only
    serializer_class = OrgMemberReadSerializer
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
            qset = User.objects.filter(email=email)
            if qset.exists():
                u = qset[0]
                org_qset = OrgMember.objects.filter(organization=org, user=u, removeDate__isnull=False)
                if org_qset.exists():
                    logInfo('CreateOrgMember: re-activate existing membership for {0}'.format(u))
                    instance = org_qset[0]
                    instance.removeDate = None
                    instance.save()
                    return instance
                error_msg = 'The email {0} already belongs to another user account.'.format(email)
                logWarning(logger, self.request, error_msg)
                raise serializers.ValidationError(error_msg)
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
        if email:
            qset = User.objects.filter(email=email).exclude(pk=m.pk)
            if qset.exists():
                error_msg = 'The email {0} already belongs to another user account.'.format(email)
                logWarning(logger, self.request, error_msg)
                raise serializers.ValidationError(error_msg)
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