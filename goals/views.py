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

class UserGoalList(generics.ListAPIView):
    serializer_class = UserGoalReadSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        user = self.request.user
        return UserGoal.objects.filter(user=user).select_related('goal','license').order_by('status', 'dueDate')


class UpdateUserLicenseGoal(LogValidationErrorMixin, generics.UpdateAPIView):
    """
    Update User License goal
    """
    serializer_class = UpdateUserLicenseGoalSerializer
    permission_classes = (permissions.IsAuthenticated, TokenHasReadWriteScope)

    def get_queryset(self):
        return UserGoal.objects.select_related('license')

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
        self.perform_update(in_serializer)
        instance = UserGoal.objects.get(pk=instance.pk)
        out_serializer = UserGoalReadSerializer(instance)
        return Response(out_serializer.data)


