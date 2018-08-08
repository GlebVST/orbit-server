import logging
from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers
from .models import *
from users.serializers import DocumentReadSerializer, StateLicenseSubSerializer

logger = logging.getLogger('gen.gsrl')

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
        return obj.getDaysLeft()


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
        return obj.getDaysLeft()

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
        return obj.computeProgress()

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
            'title',
            'dueDate',
            'status',
            'progress',
            'documents',
            'extra',
            'created',
            'modified'
        )
        read_only_fields = fields


class UpdateUserLicenseGoalSerializer(serializers.Serializer):
    licenseNumber = serializers.CharField(max_length=40)
    expireDate = serializers.DateTimeField()
    documents = serializers.PrimaryKeyRelatedField(
        queryset=Document.objects.all(),
        many=True,
        required=False
    )

    class Meta:
        fields = (
            'id',
            'licenseNumber',
            'expireDate',
            'documents'
        )

    def update(self, instance, validated_data):
        """Update usergoal.license and usergoal"""
        license = instance.license
        licenseNumber = validated_data.get('licenseNumber')
        expireDate = validated_data.get('expireDate')
        docs = validated_data.get('documents', [])
        updateGoals = False
        now = timezone.now()
        if expireDate != license.expireDate:
            logger.info('Update dueDate using this license.')
            updateGoals = True
        # update license and usergoal
        license.licenseNumber = licenseNumber
        license.expireDate = expireDate
        license.save()
        # Update usergoal instance
        instance.dueDate = expireDate
        instance.status = UserGoal.PASTDUE if expireDate < now else UserGoal.IN_PROGRESS
        instance.save()
        if docs:
            for d in docs:
                instance.documents.add(d)
        return instance

class UpdateUserWellnessGoalSerializer(serializers.Serializer):
    completeDate = serializers.DateTimeField()
    documents = serializers.PrimaryKeyRelatedField(
        queryset=Document.objects.all(),
        many=True,
        required=False
    )

    class Meta:
        fields = (
            'id',
            'completeDate',
            'documents'
        )

    def update(self, instance, validated_data):
        """Update usergoal and create new usergoal if needed"""
        completeDate = validated_data['completeDate']
        instance.completeDate = completeDate
        instance.save()
        if docs:
            for d in docs:
                instance.documents.add(d)
        user = instance.user
        basegoal = instance.goal
        wgoal = basegoal.wellnessgoal
        if not wgoal.isOneOff():
            year = instance.dueDate.year + 1
            nextDueDate = wgoal.makeDueDate(year, instance.dueDate.month, instance.dueDate.day)
            if not UserGoal.objects.filter(user=user, goal=basegoal, dueDate=nextDueDate).exists():
                usergoal = UserGoal.objects.create(
                        user=user,
                        goal=basegoal,
                        dueDate=nextDueDate,
                        status=UserGoal.IN_PROGRESS
                    )
                logger.info('Created UserGoal: {0}'.format(usergoal))
        return instance
