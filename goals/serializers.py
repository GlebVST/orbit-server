from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers
from .models import *
from users.serializers import DocumentReadSerializer, StateLicenseSubSerializer

class GoalTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoalType
        fields = ('id', 'name','description')


class CmeGoalSubSerializer(serializers.ModelSerializer):
    articlesLeft = serializers.SerializerMethodField()

    class Meta:
        model = UserGoal
        fields = (
            'articlesLeft',
        )

    def get_articlesLeft(self, obj):
        return 2


class WellnessGoalSubSerializer(serializers.ModelSerializer):
    daysLeft = serializers.SerializerMethodField()

    class Meta:
        model = UserGoal
        fields = (
            'daysLeft',
        )

    def get_daysLeft(self, obj):
        return 120


class LicenseGoalSubSerializer(serializers.ModelSerializer):
    daysLeft = serializers.SerializerMethodField()
    license = serializers.SerializerMethodField()

    class Meta:
        model = UserGoal
        fields = (
            'daysLeft',
            'license'
        )

    def get_daysLeft(self, obj):
        return 32

    def get_license(self, obj):
        s = StateLicenseSubSerializer(obj.license)
        return s.data

class UserGoalReadSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id', read_only=True)
    goalTypeId = serializers.PrimaryKeyRelatedField(source='goal.goalType.id', read_only=True)
    goalType = serializers.StringRelatedField(source='goal.goalType.name', read_only=True)
    documents = DocumentReadSerializer(many=True, required=False)
    title = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    extra = serializers.SerializerMethodField()

    def get_progress(self, obj):
        return 80

    def get_title(self, obj):
        gtype = obj.goal.goalType.name
        if gtype == GoalType.CME:
            return obj.cmeTag.name
        elif gtype == GoalType.LICENSE:
            return obj.goal.licensegoal.title
        else:
            return obj.goal.wellnessgoal.title

    def get_extra(self, obj):
        gtype = obj.goal.goalType.name
        if gtype == GoalType.CME:
            s = CmeGoalSubSerializer(obj)
        elif gtype == GoalType.LICENSE:
            s = LicenseGoalSubSerializer(obj)
        else:
            s = WellnessGoalSubSerializer(obj)
        return s.data  # <class 'rest_framework.utils.serializer_helpers.ReturnDict'>

    class Meta:
        model = UserGoal
        fields = (
            'id',
            'user',
            'goalType',
            'goalTypeId',
            'dueDate',
            'completeDate',
            'status',
            'documents',
            'extra',
            'progress',
            'title',
            'created',
            'modified'
        )
        read_only_fields = fields


