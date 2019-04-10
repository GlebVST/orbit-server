import logging
import math
from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers
from .models import *
from users.models import (
    CreditType,
    RecAllowedUrl,
    LicenseType,
    State,
    LicenseType,
    StateLicense,
    User
)
from users.serializers import DocumentReadSerializer, NestedStateLicenseSerializer
from users.feed_serializers import OrbitCmeOfferSerializer

logger = logging.getLogger('gen.gsrl')
PUB_DATE_FORMAT = '%b %Y'
OVERDUE = 'Overdue'
COMPLETED = 'Completed'
EXPIRING = 'Expiring'
ON_TRACK = 'On Track'

class GoalTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoalType
        fields = ('id', 'name','description')

class LicenseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LicenseType
        fields = ('id', 'name')


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
    title = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    extra = serializers.SerializerMethodField()
    state = serializers.PrimaryKeyRelatedField(read_only=True)

    def get_progress(self, obj):
        return obj.progress

    def get_title(self, obj):
        gtype = obj.goal.goalType.name
        if gtype != GoalType.CME or obj.cmeTag:
            return obj.title
        return obj.title + ' in ' + obj.formatCreditTypes()

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
            'extra',
            'created',
            'modified'
        )
        read_only_fields = fields


class UserLicenseGoalSummarySerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id', read_only=True)
    state = serializers.PrimaryKeyRelatedField(read_only=True)
    displayStatus = serializers.SerializerMethodField()
    state_abbrev = serializers.ReadOnlyField(source='state.abbrev')
    state_name = serializers.ReadOnlyField(source='state.name')
    licenseNumber = serializers.ReadOnlyField(source='license.licenseNumber')
    licenseType = serializers.ReadOnlyField(source='license.licenseType.name')
    licenseTypeId = serializers.ReadOnlyField(source='license.licenseType.id')

    class Meta:
        model = UserGoal
        fields = (
            'id',
            'user',
            'state',
            'state_abbrev',
            'state_name',
            'dueDate',
            'status',
            'displayStatus',
            'licenseNumber',
            'licenseType',
            'licenseTypeId',
        )
        read_only_fields = fields

    def get_licenseNumber(self, obj):
        return obj.license.licenseNumber

    def get_displayStatus(self, obj):
        """UI display value for status"""
        if obj.status == UserGoal.PASTDUE:
            return OVERDUE
        if obj.status == UserGoal.COMPLETED:
            return COMPLETED
        # check if goal dueDate is expiring
        if obj.isExpiring():
            return EXPIRING
        return ON_TRACK

class UserCreditGoalSummarySerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id', read_only=True)
    goalType = serializers.StringRelatedField(source='goal.goalType.name', read_only=True)
    state = serializers.PrimaryKeyRelatedField(read_only=True)
    cmeTag = serializers.ReadOnlyField(source='cmeTag.name')
    creditsLeft = serializers.SerializerMethodField()
    creditTypes = serializers.SerializerMethodField()
    license = serializers.SerializerMethodField()
    displayStatus = serializers.SerializerMethodField()

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
            'license',
            'displayStatus'
        )

    def get_creditsLeft(self, obj):
        """returns full creditsDue"""
        return roundCredits(float(obj.creditsDue))

    def get_creditTypes(self, obj):
        qset = obj.creditTypes.all()
        return [NestedCreditTypeSerializer(m).data for m in qset]

    def get_license(self, obj):
        """Return state info or board info"""
        if obj.state:
            # state-specifc cme/srcme goal
            return "{0.state.name} ({0.state.abbrev})".format(obj)
        # Board/Hospital cme goal
        return obj.goal.cmegoal.entityName

    def get_displayStatus(self, obj):
        """UI display value for status"""
        if obj.status == UserGoal.PASTDUE:
            return OVERDUE
        if obj.status == UserGoal.COMPLETED:
            return COMPLETED
        # check if goal dueDate is expiring
        if obj.isExpiring():
            return EXPIRING
        return ON_TRACK


class UserLicenseCreateSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(
            queryset=User.objects.all())
    state = serializers.PrimaryKeyRelatedField(
            queryset=State.objects.all())
    licenseType = serializers.PrimaryKeyRelatedField(
            queryset=LicenseType.objects.all())
    class Meta:
        model = StateLicense
        fields = (
            'id',
            'user',
            'state',
            'licenseType',
            'licenseNumber',
            'expireDate'
        )

    def create(self, validated_data):
        """Create new StateLicense and update user profile
        Returns: StateLicense instance
        """
        user = validated_data['user']
        licenseType = validated_data['licenseType']
        state = validated_data['state']
        expireDate = validated_data['expireDate']
        expireDate = expireDate.replace(hour=12)
        # create StateLicense instance
        license = super(UserLicenseCreateSerializer, self).create(validated_data)
        # update profile
        profile = user.profile
        if licenseType.name == LicenseType.TYPE_STATE:
            profile.states.add(state)
        elif licenseType.name == LicenseType.TYPE_DEA:
            profile.deaStates.add(state)
            profile.hasDEA = 1
        profile.addOrActivateCmeTags()
        return license

class UserLicenseGoalUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = StateLicense
        fields = (
            'licenseNumber',
            'expireDate',
        )

    def update(self, instance, validated_data):
        """Renew or edit-in-place the given statelicense and its associated usergoal. This expects pre-validation to check that the user licensegoal is not already archived.
        Returns: UserGoal instance
        """
        license = instance
        usergoal = license.usergoals.exclude(status=UserGoal.EXPIRED).order_by('-dueDate')[0]
        licenseNumber = validated_data.get('licenseNumber', license.licenseNumber)
        expireDate = validated_data.get('expireDate', license.expireDate)
        if expireDate:
            expireDate = expireDate.replace(hour=12)
        renewLicense = False
        updateUserCreditGoals = False
        # Decide if renew license or edit in-place (e.g. correction)
        if license.isUnInitialized():
            # An uninitialized license will be edited
            renewLicense = False
        elif license.checkExpireDateForRenewal(expireDate):
            # new expireDate meets cutoff for license renewal
            renewLicense = True
        if renewLicense:
            newLicense = StateLicense.objects.create(
                    user=license.user,
                    state=license.state,
                    licenseType=license.licenseType,
                    licenseNumber=license.licenseNumber,
                    expireDate=expireDate
                )
            logger.info('Renewed License: {0}'.format(newLicense))
            newUserLicenseGoal = UserGoal.objects.renewLicenseGoal(usergoal, newLicense)
            ugs = UserGoal.objects.updateCreditGoalsForRenewLicense(usergoal, newUserLicenseGoal, newLicense)
            return newUserLicenseGoal
        # else: update license and usergoal in-place
        logger.info('Edit existing license {0.pk}'.format(license))
        license.licenseNumber = licenseNumber
        if expireDate and expireDate != license.expireDate:
            license.expireDate = expireDate
            updateUserCreditGoals = True
        license.save()
        # Update usergoal instance
        if expireDate and expireDate != usergoal.dueDate:
            usergoal.dueDate = expireDate
            usergoal.save(update_fields=('dueDate',))
            usergoal.recompute() # update status/compliance
            logger.info('Recomputed usergoal {0.pk}/{0}'.format(usergoal))
        if updateUserCreditGoals:
            ugs = UserGoal.objects.recomputeCreditGoalsForLicense(usergoal)
        return usergoal
