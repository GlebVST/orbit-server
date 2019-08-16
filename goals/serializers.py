import logging
from collections import defaultdict
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
    User,
    OrgMember
)
from users.serializers import DocumentReadSerializer, NestedStateLicenseSerializer
from users.feed_serializers import OrbitCmeOfferSerializer

logger = logging.getLogger('gen.gsrl')
PUB_DATE_FORMAT = '%b %Y'

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
    goalType = serializers.StringRelatedField(source='goal.goalType.name', read_only=True)
    state = serializers.PrimaryKeyRelatedField(read_only=True)
    displayStatus = serializers.ReadOnlyField()
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
            'goalType',
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


class UserCreditGoalSummarySerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source='user.id', read_only=True)
    goalType = serializers.StringRelatedField(source='goal.goalType.name', read_only=True)
    state = serializers.PrimaryKeyRelatedField(read_only=True)
    cmeTag = serializers.ReadOnlyField(source='cmeTag.name')
    displayStatus = serializers.ReadOnlyField()
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


class UserLicenseCreateSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(
            queryset=User.objects.all())
    state = serializers.PrimaryKeyRelatedField(
            queryset=State.objects.all())
    licenseType = serializers.PrimaryKeyRelatedField(
            queryset=LicenseType.objects.all())
    modifiedBy = serializers.PrimaryKeyRelatedField(
            queryset=User.objects.all())
    class Meta:
        model = StateLicense
        fields = (
            'user',
            'state',
            'licenseType',
            'licenseNumber',
            'expireDate',
            'modifiedBy'
        )

    def create(self, validated_data):
        """Create new StateLicense and update user profile
        Returns: StateLicense instance
        """
        user = validated_data['user']
        licenseType = validated_data['licenseType']
        state = validated_data['state']
        expireDate = validated_data.get('expireDate', None)
        if expireDate and expireDate.hour != 12:
            expireDate = expireDate.replace(hour=12)
            validated_data['expireDate'] = expireDate
        validated_data['subcatg'] = StateLicense.objects.determineSubCatg(licenseType, state, validated_data['licenseNumber'])
        # create StateLicense instance
        license = super(UserLicenseCreateSerializer, self).create(validated_data)
        # update profile
        profile = user.profile
        if licenseType.name == LicenseType.TYPE_STATE:
            profile.states.add(state)
        elif licenseType.name == LicenseType.TYPE_DEA:
            profile.deaStates.add(state)
        elif licenseType.name == LicenseType.TYPE_FLUO:
            profile.fluoroscopyStates.add(state)
        profile.addOrActivateCmeTags()
        return license

class UserLicenseGoalUpdateSerializer(serializers.ModelSerializer):

    modifiedBy = serializers.PrimaryKeyRelatedField(
            queryset=User.objects.all())
    class Meta:
        model = StateLicense
        fields = (
            'licenseNumber',
            'expireDate',
            'modifiedBy',
        )

    def update(self, instance, validated_data):
        """Renew or edit-in-place the given statelicense and its associated usergoal. This expects pre-validation to check that the user licensegoal is not already archived.
        Returns: UserGoal instance
        """
        license = instance
        licenseNumber = validated_data.get('licenseNumber', license.licenseNumber)
        expireDate = validated_data.get('expireDate', license.expireDate)
        if expireDate and expireDate.hour != 12:
            expireDate = expireDate.replace(hour=12)
        # get the license usergoal for this license
        lgt = GoalType.objects.get(name=GoalType.LICENSE)
        usergoal = license.usergoals.select_related('goal__goalType') \
            .filter(goal__goalType=lgt) \
            .exclude(status=UserGoal.EXPIRED) \
            .order_by('-dueDate')[0]
        renewLicense = False
        # Decide if renew license or edit in-place (e.g. correction)
        if license.isUnInitialized() or licenseNumber != license.licenseNumber:
            # An uninitialized license will be edited
            logger.info('Edit in-place: License {0}'.format(license))
            renewLicense = False
        elif license.checkExpireDateForRenewal(expireDate):
            # new expireDate meets cutoff for license renewal
            renewLicense = True
        subcatg = StateLicense.objects.determineSubCatg(license.licenseType, license.state, licenseNumber)
        if renewLicense:
            newLicense = StateLicense.objects.create(
                    user=license.user,
                    state=license.state,
                    licenseType=license.licenseType,
                    licenseNumber=licenseNumber,
                    expireDate=expireDate,
                    subcatg=subcatg,
                    modifiedBy=validated_data['modifiedBy']
                )
            logger.info('Renewed License: {0}'.format(newLicense))
            newUserLicenseGoal = UserGoal.objects.renewLicenseGoal(usergoal, newLicense)
            ugs = UserGoal.objects.updateCreditGoalsForRenewLicense(usergoal, newUserLicenseGoal)
            return newUserLicenseGoal
        # else: update license and usergoal in-place
        license.licenseNumber = licenseNumber
        license.subcatg = subcatg
        license.modifiedBy = validated_data['modifiedBy']
        if expireDate and expireDate != license.expireDate:
            license.expireDate = expireDate
        license.save()
        # Update usergoal instance
        if expireDate and expireDate != usergoal.dueDate:
            usergoal.dueDate = expireDate
            usergoal.save(update_fields=('dueDate',))
            usergoal.recompute() # update status/compliance
            logger.info('Recomputed usergoal {0.pk}/{0}'.format(usergoal))
            # recompute any dependent creditgoals since we changed the dueDate of the licensegoal
            ugs = UserGoal.objects.recomputeCreditGoalsForLicense(usergoal)
        return usergoal


class UserLicenseGoalRemoveSerializer(serializers.Serializer):
    ids = serializers.PrimaryKeyRelatedField(
        queryset=UserGoal.objects.select_related('license').filter(license__isnull=False),
        many=True
    )
    modifiedBy = serializers.PrimaryKeyRelatedField(
            queryset=User.objects.all())
    class Meta:
        fields = ('ids', 'modifiedBy')

    def updateSnapshot(self, orgmember):
        userdata = {} # null, plus key for each stateid in user's profile
        gts = GoalType.objects.getCreditGoalTypes()
        fkwargs = {
            'valid': True,
            'goal__goalType__in': gts,
            'is_composite_goal': False,
        }
        u = orgmember.user
        profile = u.profile
        stateids = profile.stateSet
        sl_qset = StateLicense.objects.getLatestSetForUser(u)
        userdata[None] = UserGoal.objects.compute_userdata_for_admin_view(u, fkwargs, sl_qset)
        for stateid in stateids:
            userdata[stateid] = UserGoal.objects.compute_userdata_for_admin_view(u, fkwargs, sl_qset, stateid)
        now = timezone.now()
        orgmember.snapshot = userdata
        orgmember.snapshotDate = now
        orgmember.save(update_fields=('snapshot', 'snapshotDate'))

    def save(self):
        """This should be called inside a transaction, and for the license
        usergoals of a single user only.
        Steps:
        1. Inactivate the associated user StateLicense instances and delete the usergoals.
        2. Update user profile and rematchGoals (via ProfileUpdateSerializer)
        3. Update orgmember snapshot for this user
        """
        from users.serializers import ProfileUpdateSerializer
        usergoals = self.validated_data['ids']
        user = usergoals[0].user
        profile = user.profile
        stateSet = set([s.pk for s in profile.states.all()])
        deaStateSet = set([s.pk for s in profile.deaStates.all()])
        fluoStateSet = set([s.pk for s in profile.fluoroscopyStates.all()])
        # inactivate licenses
        licenses = []
        ltypeStateDict = defaultdict(list) # (ltype, state) => [license,]
        now = timezone.now()
        for ug in usergoals:
            license = ug.license
            lt = license.licenseType
            state = license.state
            logger.info('Inactivate {0}'.format(license))
            license.inactivate(now, self.validated_data['modifiedBy'])
            licenses.append(license)
            ltypeStateDict[(lt, state)].append(license)
            # delete the license usergoal
            logger.info('Deleting license usergoal {0.pk}|{0}'.format(ug))
            ug.delete()
        # check if need to remove states from profile
        for lt, state in ltypeStateDict.keys():
            # does user have any active licenses for this pair?
            qs = user.statelicenses.filter(licenseType=lt, state=state, is_active=True).order_by('expireDate', 'pk')
            if qs.exists():
                active_sl = qs[0] # active license for (ltype, state) with the earliest expireDate
                # Check if need to transfer creditgoals
                for license in ltypeStateDict[(lt, state)]:
                    # does inactivated license have any credit goals
                    credit_ugs = UserGoal.objects.getCreditsGoalsForLicense(license)
                    if credit_ugs.exists():
                        # transfer creditgoals to the active_sl
                        ret = UserGoal.objects.transferCreditGoalsToLicense(license, active_sl)
            else:
                # user has no active licenses for (ltype, state): discard state from appropriate set
                if lt.name == LicenseType.TYPE_STATE:
                    stateSet.discard(state.pk)
                elif lt.name == LicenseType.TYPE_DEA:
                    deaStateSet.discard(state.pk)
                elif lt.name == LicenseType.TYPE_FLUO:
                    fluoStateSet.discard(state.pk)
        # Update profile (even if no discard because we still want to rematchGoals via signal)
        form_data = {
                'states': list(stateSet),
                'deaStates': list(deaStateSet),
                'fluorsocopyStates': list(fluoStateSet),
            }
        logger.info('Update profile: {0.pk}|{0}'.format(profile))
        profileUpdSer = ProfileUpdateSerializer(instance=profile, data=form_data, partial=True)
        profileUpdSer.is_valid(raise_exception=True)
        profile = profileUpdSer.save()
        # update snapshot
        orgmqs = OrgMember.objects.filter(user=user, pending=False, removeDate__isnull=True).order_by('-created')
        if orgmqs.exists():
            orgm = orgmqs[0] # OrgMember instance
            self.updateSnapshot(orgm)
        return licenses # list of inactivated licenses
