# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import pytz
from datetime import datetime
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone

from rest_framework import generics, exceptions, permissions, status, serializers
from rest_framework.filters import BaseFilterBackend
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope
# proj
from common.logutils import *
from users.permissions import IsEnterpriseAdmin, IsOwnerOrEnterpriseAdmin
# app
from .models import *
from .serializers import *

logger = logging.getLogger('api.goals')

class LogValidationErrorMixin(object):
    def handle_exception(self, exc):
        response = super(LogValidationErrorMixin, self).handle_exception(exc)
        if response is not None and isinstance(exc, exceptions.ValidationError):
            #logWarning(logger, self.request, exc.get_full_details())
            message = "ValidationError: {0}".format(exc.detail)
            #logError(logger, self.request, message)
            logWarning(logger, self.request, message)
        return response

# GoalType - list only
class GoalTypeList(generics.ListAPIView):
    queryset = GoalType.objects.all().order_by('name')
    serializer_class = GoalTypeSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

class LicenseTypeList(generics.ListAPIView):
    queryset = LicenseType.objects.all().order_by('name')
    serializer_class = LicenseTypeSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

class LongPagination(PageNumberPagination):
    page_size = 500


class UserGoalSummary(APIView):
    pagination_class = LongPagination
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get(self, request, *args, **kwargs):
        try:
            user = User.objects.get(pk=kwargs['userid'])
        except User.DoesNotExist:
            return Response({'results': []}, status=status.HTTP_404_NOT_FOUND)

        stateid = request.query_params.get('state', None)
        # get credit usergoals
        qs_license_goals = UserGoal.objects.getLicenseGoalsForUserSummary(user, stateid)
        qs_credit_goals = UserGoal.objects.getCreditGoalsForUserSummary(user, stateid)
        s_credit = UserCreditGoalSummarySerializer(qs_credit_goals, many=True)
        s_license = UserLicenseGoalSummarySerializer(qs_license_goals, many=True)
        context = {
            'credit_goals': s_credit.data,
            'licenses': s_license.data
        }
        return Response(context, status=status.HTTP_200_OK)


class UserGoalList(generics.ListAPIView):
    serializer_class = UserGoalReadSerializer
    pagination_class = LongPagination
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        qs = UserGoal.objects.filter(user=user, valid=True).select_related('goal__goalType', 'license', 'cmeTag')
        qs1 = qs.filter(status__in=[UserGoal.PASTDUE, UserGoal.IN_PROGRESS]).order_by('status', 'goal__goalType__sort_order', 'dueDate', '-modified')
        qs2 = qs.filter(status=UserGoal.COMPLETED).order_by('-modified')
        return list(qs1) + list(qs2)

class UserLicenseGoalList(generics.ListAPIView):
    serializer_class = UserLicenseGoalSummarySerializer
    pagination_class = LongPagination
    permission_classes = (permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope)

    def get_queryset(self):
        try:
            user = User.objects.get(pk=self.kwargs['userid'])
        except User.DoesNotExist:
            return Response({'results': []}, status=status.HTTP_404_NOT_FOUND)
        return UserGoal.objects.getLicenseGoalsForUserSummary(user)


class CreateUserLicenseGoal(LogValidationErrorMixin, generics.CreateAPIView):
    """
    Create new StateLicense, update profile, and assign/recompute goals for a user.
    Response: {
        id: pkeyid of UserGoal (newly created or existing goal edited-in-place)
        licenses: list of user license goals
    }
    """
    serializer_class = UserLicenseCreateSerializer
    permission_classes = (permissions.IsAuthenticated, IsEnterpriseAdmin, TokenHasReadWriteScope)

    def perform_create(self, serializer):
        """Call serializer to create new StateLicense and update profile.
        Then, handle new goal assignment.
        Returns: UserGoal instance for the new usergoal attached to the new license.
        """
        ##form_data = self.request.data
        form_data = serializer.validated_data
        expireDate = form_data['expireDate']
        createNewLicense = False
        renewLicense = False
        fkw = dict(
            is_active=True,
            user=form_data['user'],
            state=form_data['state'],
            licenseType=form_data['licenseType']
        )
        qs = StateLicense.objects.filter(**fkw).order_by('-expireDate')
        if not qs.exists():
            # Active (state, licenseType) license does not exist for user
            createNewLicense = True
        else:
            # Active (state, licenseType) license exists for user
            # Decide if need to renew license or edit in-place
            license = qs[0]
            if license.isUnInitialized():
                createNewLicense = False
            # is license attached to an updateable usergoal
            ugs = license.usergoals.exclude(status=UserGoal.EXPIRED).order_by('-dueDate')
            if ugs.exists():
                usergoal = ugs[0] # context for updateSerializer
                createNewLicense = False
                msg = 'Update existing active License: {0.displayLabel}'.format(license)
                logInfo(logger, self.request, msg)
            else:
                # No updateable usergoal.
                createNewLicense = True

        with transaction.atomic():
            if createNewLicense:
                # create StateLicense, and update user profile
                userLicense = serializer.save()
                userLicenseGoals, userCreditGoals = UserGoal.objects.handleNewStateLicenseForUser(userLicense)
                for usergoal in userLicenseGoals:
                    if usergoal.license.pk == userLicense.pk:
                        return usergoal # goal attached to newLicense
            else:
                # execute UserLicenseGoalUpdateSerializer
                upd_form_data = {
                    'id': license.pk,
                    'licenseNumber': self.request.data.get('licenseNumber'),
                    'expireDate': self.request.data.get('expireDate')
                }
                updateSerializer = UserLicenseGoalUpdateSerializer(
                        instance=license,
                        data=upd_form_data
                    )
                updateSerializer.is_valid(raise_exception=True)
                usergoal = updateSerializer.save() # renew or edit
                return usergoal # license usergoal

    def create(self, request, *args, **kwargs):
        form_data = request.data.copy()
        serializer = self.get_serializer(data=form_data)
        serializer.is_valid(raise_exception=True)
        usergoal = self.perform_create(serializer)
        user = usergoal.user
        qs_license_goals = UserGoal.objects.getLicenseGoalsForUserSummary(user)
        s_license = UserLicenseGoalSummarySerializer(qs_license_goals, many=True)
        context = {
            'id': usergoal.pk, # pkeyid of the usergoal attached to the new license
            'licenses': s_license.data
        }
        return Response(context, status=status.HTTP_201_CREATED)


class UpdateUserLicenseGoal(LogValidationErrorMixin, generics.UpdateAPIView):
    """
    This expects a license UserGoal id, licenseNumber, and expireDate.
    Based on the existing license expireDate, and the new expireDate,
    the UserLicenseGoalUpdateSerializer decides whether to edit-in-place or renew the existing license.
    If renew (new expireDate represents a license renewal):
        Create new StateLicense
        Archive old usergoal
        Create new usergoal attached to new license
        Renew any recurring credit goals dependent on license
    If edit:
        Edit existing StateLicense in-place
        Recompute existing license UserGoal
        Recompute dependent credit goals
    Response: {
        id: pkeyid of license UserGoal (either a newly created UserGoal or the existing id passed to endpoint)
        licenses: list of user license goals
    }
    """
    serializer_class = UserLicenseGoalUpdateSerializer
    permission_classes = (permissions.IsAuthenticated, IsOwnerOrEnterpriseAdmin, TokenHasReadWriteScope)

    def get_queryset(self):
        return UserGoal.objects.select_related('goal', 'license')

    def perform_update(self, serializer, format=None):
        with transaction.atomic():
            usergoal = serializer.save()
        return usergoal

    def update(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        partial = kwargs.pop('partial', False)
        usergoal = self.get_object() # UserGoal instance retrieved from get_queryset and kwargs[pk]
        logInfo(logger, request, 'UserGoal from url pk: {0.pk} {0}'.format(usergoal))
        license = usergoal.license # StateLicense instance
        form_data = request.data.copy()
        logInfo(logger, request, str(form_data))
        in_serializer = self.get_serializer(
                license,
                data=form_data,
                partial=partial)
        in_serializer.is_valid(raise_exception=True)
        # userLicenseGoal is either:
        #   same as usergoal (edit-in-place case)
        #   a new UserGoal instance (renew case)
        userLicenseGoal = self.perform_update(in_serializer)
        user = userLicenseGoal.user
        qs_license_goals = UserGoal.objects.getLicenseGoalsForUserSummary(user)
        s_license = UserLicenseGoalSummarySerializer(qs_license_goals, many=True)
        context = {
            'id': userLicenseGoal.pk,
            'licenses': s_license.data
        }
        return Response(context)

class GoalRecsList(APIView):
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get(self, request, *args, **kwargs):
        user = request.user
        try:
            usergoal = UserGoal.objects.get(pk=self.kwargs.get('pk'))
            goalType = usergoal.goal.goalType
        except UserGoal.DoesNotExist:
            return Response({'results': []}, status=status.HTTP_404_NOT_FOUND)
        else:
            if goalType.name == GoalType.CME:
                if not usergoal.cmeTag:
                    # no article recs for any Tag cmegoal
                    results = []
                qset = user.recaurls \
                    .select_related('offer', 'url__eligible_site') \
                    .filter(cmeTag=usergoal.cmeTag) \
                    .order_by('offer','id')
                s = RecAllowedUrlReadSerializer(qset[:3], many=True)
                results = s.data
            else:
                qset = usergoal.goal.recommendations.all().order_by('-created')[:3]
                s = GoalRecReadSerializer(qset, many=True)
                results = s.data
            context = {
                'results': results
            }
        return Response(context, status=status.HTTP_200_OK)
