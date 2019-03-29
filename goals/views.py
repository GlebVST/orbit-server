# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import pytz
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

        stateid = request.query_params.get('state', '')
        gts = GoalType.objects.getCreditGoalTypes()
        # get credit usergoals
        fkwargs_credit = {
            'valid': True,
            'goal__goalType__in': gts,
            'is_composite_goal': False,
            'status__in': [UserGoal.PASTDUE, UserGoal.IN_PROGRESS, UserGoal.COMPLETED]
        }
        if stateid:
            fkwargs_credit['state_id'] = stateid
        qs_credit_goals = user.usergoals \
                .filter(**fkwargs_credit) \
                .select_related('goal__goalType', 'cmeTag', 'state') \
                .order_by('dueDate', '-creditsDue')
        s_credit = UserCreditGoalSummarySerializer(qs_credit_goals, many=True)
        # get license usergoals
        fkwargs_license = {
            'valid': True,
            'goal__goalType__name': GoalType.LICENSE,
            'is_composite_goal': False,
            'status__in': [UserGoal.PASTDUE, UserGoal.IN_PROGRESS, UserGoal.COMPLETED]
        }
        if stateid:
            fkwargs_license['state_id'] = stateid
        qs_license_goals = user.usergoals \
                .filter(**fkwargs_license) \
                .select_related('goal__goalType', 'license__licenseType', 'state') \
                .order_by('dueDate', 'state')
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

class UpdateUserLicenseGoal(LogValidationErrorMixin, generics.UpdateAPIView):
    """
    Update User License goal
    """
    serializer_class = UserLicenseGoalUpdateSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        return UserGoal.objects.select_related('goal', 'license')

    def perform_update(self, serializer, format=None):
        user = self.request.user
        with transaction.atomic():
            instance = serializer.save(user=user)
        return instance

    def update(self, request, *args, **kwargs):
        """Override method to handle custom input/output data structures"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        form_data = request.data.copy()
        in_serializer = self.get_serializer(instance, data=form_data, partial=partial)
        in_serializer.is_valid(raise_exception=True)
        userLicenseGoal = self.perform_update(in_serializer)
        ##instance = UserGoal.objects.get(pk=instance.pk)
        out_serializer = UserGoalReadSerializer(userLicenseGoal)
        return Response(out_serializer.data)


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
