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
        return UserGoal.objects.filter(user=user).select_related('goal','license').order_by('dueDate')



