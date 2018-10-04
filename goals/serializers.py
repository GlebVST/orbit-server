import logging
from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers
from .models import *
from users.models import RecAllowedUrl, ARTICLE_CREDIT
from users.serializers import DocumentReadSerializer, NestedStateLicenseSerializer

logger = logging.getLogger('gen.gsrl')
PUB_DATE_FORMAT = '%b %Y'

class GoalTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoalType
        fields = ('id', 'name','description')

class RecAllowedUrlReadSerializer(serializers.ModelSerializer):
    domainTitle = serializers.ReadOnlyField(source='url.eligible_site.domain_title')
    pageTitle = serializers.SerializerMethodField()
    url = serializers.ReadOnlyField(source='url.url')
    pubDate = serializers.SerializerMethodField()
    numUsers = serializers.ReadOnlyField(source='url.numOffers')

    class Meta:
        model = RecAllowedUrl
        fields = (
            'id',
            'domainTitle',
            'pageTitle',
            'url',
            'pubDate',
            'numUsers'
        )
        read_only_fields = fields

    def get_pageTitle(self, obj):
        return obj.url.cleanPageTitle()

    def get_pubDate(self, obj):
        if obj.url.pubDate:
            return obj.url.pubDate.strftime(PUB_DATE_FORMAT)
        return None

class GoalRecReadSerializer(serializers.ModelSerializer):
    pubDate = serializers.SerializerMethodField()

    class Meta:
        model = GoalRecommendation
        fields = (
            'id',
            'domainTitle',
            'pageTitle',
            'url',
            'pubDate'
        )
        read_only_fields = fields

    def get_pubDate(self, obj):
        if obj.pubDate:
            return obj.pubDate.strftime(PUB_DATE_FORMAT)
        return None

class LicenseGoalSubSerializer(serializers.ModelSerializer):
    """UserLicenseGoal extra fields"""
    daysLeft = serializers.SerializerMethodField()
    license = serializers.SerializerMethodField()
    recommendations = serializers.SerializerMethodField()

    class Meta:
        model = UserGoal
        fields = (
            'daysLeft',
            'license',
            'recommendations'
        )

    def get_daysLeft(self, obj):
        return obj.daysLeft

    def get_license(self, obj):
        s = NestedStateLicenseSerializer(obj.license)
        return s.data

    def get_recommendations(self, obj):
        qset = obj.goal.recommendations.all().order_by('-created')[:3]
        s = GoalRecReadSerializer(qset, many=True)
        return s.data


class TrainingGoalSubSerializer(serializers.ModelSerializer):
    """UserTrainingGoal extra fields"""
    daysLeft = serializers.SerializerMethodField()
    recommendations = serializers.SerializerMethodField()

    class Meta:
        model = UserGoal
        fields = (
            'daysLeft',
            'recommendations'
        )

    def get_daysLeft(self, obj):
        return obj.daysLeft


    def get_recommendations(self, obj):
        qset = obj.goal.recommendations.all().order_by('-created')[:3]
        s = GoalRecReadSerializer(qset, many=True)
        return s.data

class CmeGoalSubSerializer(serializers.ModelSerializer):
    articlesLeft = serializers.SerializerMethodField()

    class Meta:
        model = UserGoal
        fields = (
            'articlesLeft',
        )

    def get_articlesLeft(self, obj):
        return int(float(obj.creditsDue)/ARTICLE_CREDIT)


class UserGoalReadSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id', read_only=True)
    goalTypeId = serializers.PrimaryKeyRelatedField(source='goal.goalType.id', read_only=True)
    goalType = serializers.StringRelatedField(source='goal.goalType.name', read_only=True)
    documents = DocumentReadSerializer(many=True, required=False)
    title = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    extra = serializers.SerializerMethodField()

    def get_progress(self, obj):
        return obj.progress

    def get_title(self, obj):
        return obj.title

    def get_extra(self, obj):
        gtype = obj.goal.goalType.name
        if gtype == GoalType.CME:
            s = CmeGoalSubSerializer(obj)
        elif gtype == GoalType.LICENSE:
            s = LicenseGoalSubSerializer(obj)
        else:
            s = TrainingGoalSubSerializer(obj)
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


class UserLicenseGoalUpdateSerializer(serializers.Serializer):
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
        """Update usergoal, and statelicense for this goal,
        and any user cmegoals that make use of the license expireDate
        """
        license = instance.license
        licenseNumber = validated_data.get('licenseNumber')
        expireDate = validated_data.get('expireDate')
        docs = validated_data.get('documents', [])
        updateUserCmeGoals = False
        now = timezone.now()
        if expireDate != license.expireDate:
            updateUserCmeGoals = True
        # update license and usergoal
        license.licenseNumber = licenseNumber
        license.expireDate = expireDate
        license.save()
        # Update usergoal instance
        instance.dueDate = expireDate
        instance.save(update_fields=('dueDate',))
        instance.recompute() # update status/compliance
        if docs:
            for d in docs:
                instance.documents.add(d)
        if updateUserCmeGoals:
            licenseGoal = instance.goal.licensegoal # LicenseGoal instance
            to_update = set([])
            logger.debug('Finding usergoals that depend on LicenseGoal: {0.pk}/{0}'.format(licenseGoal))
            for cmeGoal in licenseGoal.cmegoals.all():
                # Use related_name on UserGoal.cmeGoals M2Mfield
                logger.debug('cmeGoal: {0.pk}/{0}'.format(cmeGoal))
                qset = cmeGoal.usercmegoals.filter(user=instance.user)
                for ug in qset: # UserGoal qset
                    to_update.add(ug)
            for tGoal in licenseGoal.traingoals.all():
                # use related name on UserGoal.goal FK field
                logger.debug('trainGoal: {0.pk}/{0}'.format(tGoal))
                qset = tGoal.goal.usergoals.filter(user=instance.user)
                for ug in qset: # UserGoal qset
                    to_update.add(ug)
            for ug in to_update:
                ug.recompute()
        return instance

class UserTrainingGoalUpdateSerializer(serializers.Serializer):
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
        tgoal = basegoal.traingoal
        if basegoal.interval:
            year = instance.dueDate.year + basegoal.interval
            nextDueDate = makeDueDate(year, instance.dueDate.month, instance.dueDate.day)
            if not UserGoal.objects.filter(user=user, goal=basegoal, dueDate=nextDueDate).exists():
                usergoal = UserGoal.objects.create(
                        user=user,
                        goal=basegoal,
                        dueDate=nextDueDate,
                        status=UserGoal.IN_PROGRESS
                    )
                logger.info('Created UserTrainingGoal: {0}'.format(usergoal))
        return instance


