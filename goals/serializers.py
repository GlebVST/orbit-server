import logging
import math
from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers
from .models import *
from common.dateutils import makeAwareDatetime
from users.models import CreditType, RecAllowedUrl, ARTICLE_CREDIT
from users.serializers import DocumentReadSerializer, NestedStateLicenseSerializer
from users.feed_serializers import OrbitCmeOfferSerializer

logger = logging.getLogger('gen.gsrl')
PUB_DATE_FORMAT = '%b %Y'

class GoalTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoalType
        fields = ('id', 'name','description')

class NestedCreditTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditType
        fields = ('abbrev',)

class RecAllowedUrlReadSerializer(serializers.ModelSerializer):
    domainTitle = serializers.ReadOnlyField(source='url.eligible_site.domain_title')
    pageTitle = serializers.SerializerMethodField()
    url = serializers.ReadOnlyField(source='url.url')
    pubDate = serializers.SerializerMethodField()
    numUsers = serializers.ReadOnlyField(source='url.numOffers')
    offer = serializers.SerializerMethodField()

    class Meta:
        model = RecAllowedUrl
        fields = (
            'id',
            'domainTitle',
            'pageTitle',
            'url',
            'pubDate',
            'numUsers',
            'offer'
        )
        read_only_fields = fields

    def get_pageTitle(self, obj):
        return obj.url.cleanPageTitle()

    def get_pubDate(self, obj):
        if obj.url.pubDate:
            return obj.url.pubDate.strftime(PUB_DATE_FORMAT)
        return None

    def get_offer(self, obj):
        if obj.offer:
            return OrbitCmeOfferSerializer(obj.offer).data
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

def roundCredits(c):
    """Args:
        c: float
    Get diff between c and floor(c)
    if diff = 0 or dif = 0.5: return as is
    if diff < 0.5: return floor + 0.5 (round up to next 0.5)
    else return ceil (round up to next int)
    This rounds up to ensure we don't underestimate value.
    Returns: float rounded to nearest 0 or 0.5
    """
    f = math.floor(c)
    d = c - f
    if d == 0 or d == 0.5:
        return c # no change
    if d < 0.5:
        return f + 0.5
    return math.ceil(c)

class CmeGoalSubSerializer(serializers.ModelSerializer):
    creditsLeft = serializers.SerializerMethodField()
    creditTypes = serializers.SerializerMethodField()
    instructions = serializers.SerializerMethodField()

    class Meta:
        model = UserGoal
        fields = (
            'creditsLeft',
            'creditTypes',
            'instructions'
        )

    def get_creditsLeft(self, obj):
        """Return dueMonthly"""
        return roundCredits(float(obj.creditsDueMonthly))

    def get_creditTypes(self, obj):
        qset = obj.creditTypes.all()
        return [NestedCreditTypeSerializer(m).data for m in qset]

    def get_instructions(self, obj):
        """Returns cmeTag.instructions or empty str"""
        cmeTag = obj.goal.cmegoal.cmeTag
        if cmeTag:
            return cmeTag.instructions
        return ''

class SRCmeGoalSubSerializer(serializers.ModelSerializer):
    creditsLeft = serializers.SerializerMethodField()
    creditTypes = serializers.SerializerMethodField()
    instructions = serializers.SerializerMethodField()

    class Meta:
        model = UserGoal
        fields = (
            'creditsLeft',
            'creditTypes',
            'instructions'
        )

    def get_creditsLeft(self, obj):
        """returns full creditsDue"""
        return roundCredits(float(obj.creditsDue))

    def get_creditTypes(self, obj):
        qset = obj.creditTypes.all()
        return [NestedCreditTypeSerializer(m).data for m in qset]

    def get_instructions(self, obj):
        """Returns cmeTag.instructions or empty str"""
        cmeTag = obj.goal.srcmegoal.cmeTag
        if cmeTag:
            return cmeTag.instructions
        return ''

class UserGoalReadSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id', read_only=True)
    goalTypeId = serializers.PrimaryKeyRelatedField(source='goal.goalType.id', read_only=True)
    goalType = serializers.StringRelatedField(source='goal.goalType.name', read_only=True)
    is_composite_goal = serializers.ReadOnlyField()
    documents = DocumentReadSerializer(many=True, required=False)
    title = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    extra = serializers.SerializerMethodField()
    state = serializers.PrimaryKeyRelatedField(read_only=True)

    def get_progress(self, obj):
        return obj.progress

    def get_title(self, obj):
        return obj.title

    def get_extra(self, obj):
        gtype = obj.goal.goalType.name
        if gtype == GoalType.LICENSE:
            s = LicenseGoalSubSerializer(obj)
        elif gtype == GoalType.CME:
            s = CmeGoalSubSerializer(obj)
        elif gtype == GoalType.SRCME:
            s = SRCmeGoalSubSerializer(obj)
        else:
            return None
        return s.data  # <class 'rest_framework.utils.serializer_helpers.ReturnDict'>

    class Meta:
        model = UserGoal
        fields = (
            'id',
            'user',
            'goalType',
            'goalTypeId',
            'is_composite_goal',
            'state',
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


class UserGoalSummarySerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id', read_only=True)
    goalType = serializers.StringRelatedField(source='goal.goalType.name', read_only=True)
    state = serializers.PrimaryKeyRelatedField(read_only=True)
    cmeTag = serializers.ReadOnlyField(source='cmeTag.name')
    creditsLeft = serializers.SerializerMethodField()
    creditTypes = serializers.SerializerMethodField()
    license = serializers.SerializerMethodField()

    class Meta:
        model = UserGoal
        fields = (
            'id',
            'user',
            'goalType',
            'state',
            'dueDate',
            'status',
            'cmeTag',
            'creditsLeft',
            'creditTypes',
            'license'
        )

    def get_creditsLeft(self, obj):
        """returns full creditsDue"""
        return roundCredits(float(obj.creditsDue))

    def get_creditTypes(self, obj):
        qset = obj.creditTypes.all()
        return [NestedCreditTypeSerializer(m).data for m in qset]

    def get_license(self, obj):
        """Return state/licenseType or board info"""
        license = obj.license
        if license:
            ltype = license.licenseType.name
            if ltype == 'Medical Board':
                return "{0.state.name} ({0.state.abbrev})".format(obj)
            return '{0} {1.name} ({0.state.abbrev})'.format(ltype, obj.state)
        if obj.state:
            return "{0.state.name} ({0.state.abbrev})".format(obj)
        # else: expect this is a Board/Hospital goal
        return obj.goal.cmegoal.entityName



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
        user = instance.user
        license = instance.license
        licenseNumber = validated_data.get('licenseNumber')
        expireDate = validated_data.get('expireDate')
        createNewLicense = False
        updateUserCreditGoals = False
        now = timezone.now()
        # Decide if need to create a new license or edit in-place (e.g. correction)
        if license.licenseNumber and license.expireDate and expireDate > license.expireDate:
            tdiff = expireDate - license.expireDate
            if tdiff.days >= 365:
                createNewLicense = True # create new license instance
        if createNewLicense:
            newLicense = StateLicense.objects.create(
                    user=user,
                    state=license.state,
                    licenseType=license.licenseType,
                    licenseNumber=license.licenseNumber,
                    expireDate=expireDate
                )
            newUserLicenseGoal = UserGoal.objects.renewLicenseGoal(instance, newLicense)
            if 'documents' in validated_data:
                docs = validated_data['documents']
                newUserLicenseGoal.documents.set(docs)
            ugs = UserGoal.objects.updateCreditGoalsForRenewLicense(instance, newUserLicenseGoal)
            return newUserLicenseGoal
        # else
        if expireDate != license.expireDate:
            updateUserCreditGoals = True
        # update license and usergoal in-place
        license.licenseNumber = licenseNumber
        license.expireDate = expireDate
        license.save()
        # Update usergoal instance
        instance.dueDate = expireDate
        instance.save(update_fields=('dueDate',))
        instance.recompute() # update status/compliance
        if 'documents' in validated_data:
            docs = validated_data['documents']
            instance.documents.set(docs)
        if updateUserCreditGoals:
            UserGoal.objects.recomputeCreditGoalsForLicense(instance)
        return instance
