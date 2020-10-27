import logging
from urllib.parse import urlparse, urldefrag
from rest_framework import serializers
from common.appconstants import GROUP_ENTERPRISE_MEMBER
from common.signals import profile_saved
from .models import *

logger = logging.getLogger('gen.srl')

class DegreeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Degree
        fields = ('id', 'abbrev', 'name', 'sort_order')


class HospitalSerializer(serializers.ModelSerializer):
    state = serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta:
        model = Hospital
        fields = ('id', 'state', 'city', 'display_name')

class NestedHospitalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hospital
        fields = ('id', 'display_name')

class LicenseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LicenseType
        fields = ('id', 'name')

class NestedResidencySerializer(serializers.ModelSerializer):
    class Meta:
        model = ResidencyProgram
        fields = ('id', 'name')


class CmeTagWithSpecSerializer(serializers.ModelSerializer):
    specialties = serializers.PrimaryKeyRelatedField(
        queryset=PracticeSpecialty.objects.all(),
        many=True
    )
    class Meta:
        model = CmeTag
        fields = ('id', 'name', 'priority', 'description', 'specialties', 'srcme_only', 'exemptFrom1Tag', 'instructions')

class ResidencyProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResidencyProgram
        fields = ('id', 'name')


# Used by auth_view to serialize the SA-CME tag
class ActiveCmeTagSerializer(serializers.ModelSerializer):
    is_active = serializers.SerializerMethodField()
    categoryid = serializers.ReadOnlyField(source='category.id')
    category_name = serializers.ReadOnlyField(source='category.name')

    def get_is_active(self, obj):
        return True

    class Meta:
        model = CmeTag
        fields = (
            'id',
            'name',
            'priority',
            'description',
            'is_active',
            'srcme_only',
            'exemptFrom1Tag',
            'instructions',
            'categoryid',
            'category_name'
        )


class NestedStateSerializer(serializers.ModelSerializer):

    class Meta:
        model = State
        fields = ('id', 'abbrev', 'name', 'rnCertValid')

class CountrySerializer(serializers.ModelSerializer):
    states = NestedStateSerializer(many=True, read_only=True)

    class Meta:
        model = Country
        fields = ('id', 'code', 'name', 'states')

class StateSerializer(serializers.ModelSerializer):
    country = serializers.PrimaryKeyRelatedField(queryset=Country.objects.all())

    class Meta:
        model = State
        fields = ('id', 'country', 'abbrev', 'name', 'rnCertValid')


class NestedSubSpecialtySerializer(serializers.ModelSerializer):

    class Meta:
        model = SubSpecialty
        fields = ('id', 'name',)

class PracticeSpecialtyListSerializer(serializers.ModelSerializer):
    subspecialties = NestedSubSpecialtySerializer(many=True, read_only=True)
    class Meta:
        model = PracticeSpecialty
        fields = ('id', 'name', 'planText','subspecialties')

class PracticeSpecialtySerializer(serializers.ModelSerializer):
    cmeTags = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
        many=True
    )
    planText = serializers.CharField(max_length=500, default='')

    class Meta:
        model = PracticeSpecialty
        fields = ('id', 'name', 'cmeTags', 'planText')

class ProfileCmetagSerializer(serializers.ModelSerializer):
    """Used by ProfileReadSerializer and ProfileUpdateSerializer"""
    id = serializers.ReadOnlyField(source='tag.id')
    name = serializers.ReadOnlyField(source='tag.name')
    priority = serializers.ReadOnlyField(source='tag.priority')
    description = serializers.ReadOnlyField(source='tag.description')
    srcme_only = serializers.ReadOnlyField(source='tag.srcme_only')
    exemptFrom1Tag = serializers.ReadOnlyField(source='tag.exemptFrom1Tag')
    instructions = serializers.ReadOnlyField(source='tag.instructions')
    categoryid = serializers.ReadOnlyField(source='tag.category.id')
    category_name = serializers.ReadOnlyField(source='tag.category.name')

    class Meta:
        model = ProfileCmetag
        fields = (
            'id',
            'name',
            'priority',
            'description',
            'is_active',
            'srcme_only',
            'exemptFrom1Tag',
            'instructions',
            'categoryid',
            'category_name'
        )

class ProfileCmetagUpdateSerializer(serializers.ModelSerializer):
    tag = serializers.PrimaryKeyRelatedField(
        queryset=CmeTag.objects.all(),
    )
    is_active = serializers.BooleanField()

    class Meta:
        model = ProfileCmetag
        fields = ('tag','is_active')

class ManageProfileCmetagSerializer(serializers.Serializer):
    """Updates the is_active flag of a list of existing ProfileCmetags for a given user"""
    tags = ProfileCmetagUpdateSerializer(many=True)

    def update(self, instance, validated_data):
        """Update ProfileCmetag for user and emit profile_saved signal"""
        user = instance.user
        data = validated_data['tags']
        for d in data:
            t = d['tag']
            is_active = d['is_active']
            try:
                pct = ProfileCmetag.objects.get(profile=instance, tag=t)
            except ProfileCmetag.DoesNotExist:
                pct = ProfileCmetag.objects.create(profile=instance, tag=t, is_active=is_active)
            else:
                if pct.is_active != is_active:
                    pct.is_active = is_active
                    pct.save()
                    logger.info('Updated ProfileCmetag {0}'.format(pct))
        # emit profile_saved signal
        if instance.allowUserGoals():
            ret = profile_saved.send(sender=instance.__class__, user_id=user.pk)
        return instance

class ProfileInitialUpdateSerializer(serializers.ModelSerializer):
    """Used for initial user intake screen : name and country
    and for the case of changing initial planId. If new planId
    is isFreeIndividual, a new UserSubscription is created.
    """
    id = serializers.IntegerField(source='user.id', read_only=True)
    country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        allow_null=True
    )

    class Meta:
        model = Profile
        fields = (
            'id',
            'firstName',
            'lastName',
            'country',
            'planId',
        )

    def update(self, instance, validated_data):
        key = 'planId'
        if key in validated_data:
            if not validated_data[key]:
                validated_data[key] = instance.planId
        user = instance.user
        oldPlanId = instance.planId
        # update the instance
        instance = super(ProfileInitialUpdateSerializer, self).update(instance, validated_data)
        if instance.planId and not user.subscriptions.exists():
            # check if need to create Free UserSubs
            plan = SubscriptionPlan.objects.get(planId=instance.planId)
            if plan.isFreeIndividual():
                us = UserSubscription.objects.createFreeSubscription(user, plan)
                logger.info('Create free UserSubs {0.user}/{0.subscriptionId}'.format(us))
        return instance


class ProfileUpdateSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    npiNumber = serializers.CharField(max_length=20, allow_blank=True)
    ABANumber = serializers.CharField(required=False, max_length=10, allow_blank=True)
    ABIMNumber = serializers.CharField(required=False, max_length=10, allow_blank=True)
    birthDate = serializers.DateField(required=False, allow_null=True)
    residencyEndDate = serializers.DateField(required=False, allow_null=True)
    country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        allow_null=True
    )
    residency_program = serializers.PrimaryKeyRelatedField(
        queryset=ResidencyProgram.objects.all(),
        required=False,
        allow_null=True
    )
    degrees = serializers.PrimaryKeyRelatedField(
        queryset=Degree.objects.all(),
        many=True
    )
    specialties = serializers.PrimaryKeyRelatedField(
        queryset=PracticeSpecialty.objects.all(),
        many=True
    )
    subspecialties = serializers.PrimaryKeyRelatedField(
        queryset=SubSpecialty.objects.all(),
        many=True
    )
    states = serializers.PrimaryKeyRelatedField(
        queryset=State.objects.all(),
        many=True
    )
    deaStates = serializers.PrimaryKeyRelatedField(
        queryset=State.objects.all(),
        many=True
    )
    fluoroscopyStates = serializers.PrimaryKeyRelatedField(
        queryset=State.objects.all(),
        #required=False,
        many=True,
    )
    hospitals = serializers.PrimaryKeyRelatedField(
        queryset=Hospital.objects.all(),
        many=True
    )
    cmeTags = serializers.SerializerMethodField()

    def get_cmeTags(self, obj):
        qset = ProfileCmetag.objects.filter(profile=obj)
        return [ProfileCmetagSerializer(m).data for m in qset]

    class Meta:
        model = Profile
        fields = (
            'id',
            'firstName',
            'lastName',
            'country',
            'organization',
            'residency_program',
            'birthDate',
            'residencyEndDate',
            'affiliationText',
            'interestText',
            'planId',
            'inviteId',
            'socialId',
            'pictureUrl',
            'ABANumber',
            'ABIMNumber',
            'npiNumber',
            'npiFirstName',
            'npiLastName',
            'npiType',
            'nbcrnaId',
            'cmeTags',
            'degrees',
            'specialties',
            'subspecialties',
            'states',
            'deaStates',
            'fluoroscopyStates',
            'hospitals',
            'verified',
            'accessedTour',
            'cmeStartDate',
            'cmeEndDate',
        )
        read_only_fields = (
            'organization',
            'cmeTags',
            'planId',
            'inviteId',
            'socialId',
            'pictureUrl',
            'verified',
            'accessedTour',
        )

    def update(self, instance, validated_data):
        """
        If specialties/subspecialties/states are updated: handle cmeTags assignment
        Emit profile_saved signal for enterprise members at the end.
        """
        user = instance.user
        #logger.info(str(validated_data))
        # get current data before updating the instance
        curDegs = set([m for m in instance.degrees.all()])
        curSpecs = set([m for m in instance.specialties.all()])
        curSubSpecs = set([m for m in instance.subspecialties.all()])
        curStates = set([m for m in instance.states.all()])
        curDeaStates = set([m for m in instance.deaStates.all()])
        curFluoroStates = set([m for m in instance.fluoroscopyStates.all()])
        # update the instance
        instance = super(ProfileUpdateSerializer, self).update(instance, validated_data)
        #newFluoroStates = ",".join([m.abbrev for m in instance.fluoroscopyStates.all()])
        #logger.info('User {0.pk} fluoroscopyStates: {0}'.format(user, newFluoroStates))

        add_tags, created_tags = instance.addOrActivateCmeTags() # (active tags, newly created tags)
        del_tags = set([]) # tags to be removed or deactivated
        fieldName = 'degrees'
        if fieldName in validated_data:
            # need to check if key exists, because a PATCH request may not contain the fieldName
            newDegs = set([deg for deg in validated_data[fieldName]])
            delDegs = curDegs.difference(newDegs) # difference between old and new are the ones removed
            for deg in delDegs:
                if deg.abbrev == Degree.DO:
                    # delete DO tags
                    for state in curStates:
                        for t in state.doTags.all():
                            del_tags.add(t)
                logger.info('User {0}: remove Degree: {1}'.format(user, deg))
        # now handle cmeTags
        fieldName = 'specialties'
        if fieldName in validated_data:
            # need to check if key exists, because a PATCH request may not contain the fieldName
            newSpecs = set([ps for ps in validated_data[fieldName]])
            delSpecs = curSpecs.difference(newSpecs) # difference between old and new are the ones removed
            for ps in delSpecs:
                logger.info('User {0}: remove PracticeSpecialty: {1}'.format(user, ps))
            delspectags = CmeTag.objects.filter(name__in=[ps.name for ps in delSpecs])
            for t in delspectags:
                del_tags.add(t)
        fieldName = 'subspecialties'
        if fieldName in validated_data:
            newSubSpecs = set([ps for ps in validated_data[fieldName]])
            delSubSpecs = curSubSpecs.difference(newSubSpecs)
            for ps in delSubSpecs:
                logger.info('User {0}: remove SubSpecialty: {1}'.format(user, ps))
                for t in ps.cmeTags.all():
                    del_tags.add(t)
        fieldName = 'states'
        if fieldName in validated_data:
            newStates = set([ps for ps in validated_data[fieldName]])
            delStates = curStates.difference(newStates)
            for state in delStates:
                logger.info('User {0} : remove State: {1}'.format(user, state))
                for t in state.cmeTags.all():
                    del_tags.add(t)
                for t in state.deaTags.all():
                    del_tags.add(t)
        moctag = CmeTag.objects.get(name=CmeTag.ABIM_MOC)
        if ProfileCmetag.objects.filter(profile=instance, tag=moctag).exists():
            if not instance.isProfileCompleteForMOC():
                logger.info('User {0}: no longer eligible for CmeTag: {1}'.format(user, moctag))
                del_tags.add(moctag)
        # Filter del_tags so it does not contain anything in add_tags
        rtags = add_tags.intersection(del_tags)
        for t in rtags:
            del_tags.remove(t)

        # Process del_tags: delete if unused, else inactivate
        for t in del_tags:
            qset = ProfileCmetag.objects.filter(profile=instance, tag=t)
            if not qset.exists():
                continue
            pct = qset[0]
            num_entries = t.entries.filter(user=user).count()
            if num_entries == 0:
                pct.delete()
                logger.info('Delete unused ProfileCmetag: {0}'.format(pct))
            elif pct.is_active:
                pct.is_active = False
                pct.save(update_fields=('is_active',))
                logger.info('Inactivate ProfileCmetag: {0}'.format(pct))
        # Process created_tags
        for t in created_tags:
            if t.pk == moctag.pk:
                # Apply tag to any existing offers for user
                OrbitCmeOffer.objects.addTagToUserOffers(user, t)
        # emit profile_saved signal
        if instance.allowUserGoals():
            ret = profile_saved.send(sender=instance.__class__, user_id=user.pk)
        return instance


class ProfileReadSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    country = serializers.PrimaryKeyRelatedField(read_only=True)
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    # list of pkeyids
    degrees = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    specialties = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    subspecialties = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    hospitals = NestedHospitalSerializer(many=True, read_only=True)
    states = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    deaStates = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    fluoroscopyStates = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    isSignupComplete = serializers.SerializerMethodField()
    isNPIComplete = serializers.SerializerMethodField()
    shouldReqABANumber = serializers.SerializerMethodField()
    shouldReqABIMNumber = serializers.SerializerMethodField()
    profileComplete = serializers.SerializerMethodField()
    cmeTags = serializers.SerializerMethodField()
    residency_program = serializers.SerializerMethodField()

    def get_isSignupComplete(self, obj):
        return obj.isSignupComplete()

    def get_isNPIComplete(self, obj):
        return obj.isNPIComplete()

    def get_shouldReqABANumber(self, obj):
        return obj.shouldReqABANumber()

    def get_shouldReqABIMNumber(self, obj):
        return obj.shouldReqABIMNumber()

    def get_profileComplete(self, obj):
        return obj.measureComplete()

    def get_cmeTags(self, obj):
        qset = ProfileCmetag.objects.filter(profile=obj)
        return [ProfileCmetagSerializer(m).data for m in qset]

    def get_residency_program(self, obj):
        if obj.residency_program:
            s = NestedResidencySerializer(obj.residency_program)
            return s.data
        return None

    class Meta:
        model = Profile
        fields = (
            'id',
            'firstName',
            'lastName',
            'country',
            'organization',
            'residency_program',
            'birthDate',
            'residencyEndDate',
            'affiliationText',
            'interestText',
            'planId',
            'inviteId',
            'socialId',
            'pictureUrl',
            'ABANumber',
            'ABIMNumber',
            'npiNumber',
            'npiFirstName',
            'npiLastName',
            'npiType',
            'nbcrnaId',
            'cmeTags',
            'degrees',
            'specialties',
            'subspecialties',
            'states',
            'deaStates',
            'fluoroscopyStates',
            'hospitals',
            'verified',
            'accessedTour',
            'cmeStartDate',
            'cmeEndDate',
            'shouldReqABANumber',
            'shouldReqABIMNumber',
            'isNPIComplete',
            'isSignupComplete',
            'profileComplete',
            'created',
            'modified'
        )
        read_only_fields = fields



class StateLicenseSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    state = serializers.PrimaryKeyRelatedField(read_only=True)
    licenseType = serializers.StringRelatedField(read_only=True)
    class Meta:
        model = StateLicense
        fields = ('id','user', 'state', 'licenseType', 'licenseNumber', 'expireDate')

# Nested version used by AuditReport and goals
class NestedStateLicenseSerializer(serializers.ModelSerializer):
    state = serializers.StringRelatedField(read_only=True)
    licenseType = serializers.StringRelatedField(read_only=True)
    class Meta:
        model = StateLicense
        fields = ('state','licenseType', 'licenseNumber', 'expireDate')


class UserFeedbackSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    entry = serializers.PrimaryKeyRelatedField(
            queryset=Entry.objects.all(),
            allow_null=True,
            required=False
    )
    class Meta:
        model = UserFeedback
        fields = ('id', 'user', 'entry', 'message', 'hasBias', 'hasUnfairContent')

class EligibleSiteSerializer(serializers.ModelSerializer):
    specialties = serializers.PrimaryKeyRelatedField(
        queryset=PracticeSpecialty.objects.all(),
        many=True,
        required=False
    )
    needs_ad_block = serializers.BooleanField(default=False)
    all_specialties = serializers.BooleanField(default=False)
    is_unlisted = serializers.BooleanField(default=False)
    class Meta:
        model = EligibleSite
        fields = (
            'id',
            'site_type',
            'domain_name',
            'journal_home_page',
            'domain_title',
            'example_url',
            'example_title',
            'description',
            'specialties',
            'all_specialties',
            'needs_ad_block',
            'is_unlisted'
        )

    def create(self, validated_data):
        """Create EligibleSite instance
        Add example_url.netloc to AllowedHost
        Add example_url to AllowedUrl
        """
        instance = super(EligibleSiteSerializer, self).create(validated_data)
        example_url = urldefrag(validated_data['example_url'])[0]
        res = urlparse(example_url)
        is_secure = res.scheme == 'https'
        netloc = res.netloc
        # create AllowedHost
        host, created = AllowedHost.objects.get_or_create(hostname=netloc)
        if created:
            logger.info('EligibleSite: new AllowedHost: {0}'.format(netloc))
            if is_secure:
                host.is_secure = True
                host.save(update_fields=('is_secure',))
        # create AllowedUrl
        page_title = validated_data.get('example_title')
        qs = AllowedUrl.objects.filter(url=example_url)
        if not qs.exists():
            aurl = AllowedUrl.objects.create(
                host=host,
                eligible_site=instance,
                url=example_url,
                page_title=page_title
            )
            logger.info('CreateEligibleSite: new AllowedUrl: {0}'.format(aurl))
        else:
            logger.warning('CreateEligibleSite: AllowedUrl already exists: {0}'.format(aurl))
        return instance


class DocumentReadSerializer(serializers.ModelSerializer):
    url = serializers.FileField(source='document', max_length=None, allow_empty_file=False, use_url=True)
    class Meta:
        model = Document
        fields = (
            'id',
            'url',
            'name',
            'md5sum',
            'content_type',
            'image_h',
            'image_w',
            'is_thumb',
            'is_certificate'
        )
        read_only_fields = ('name','md5sum','content_type','image_h','image_w', 'is_thumb','is_certificate')

# Used by payment_views and auth_views
class UserSubsReadSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    plan_type = serializers.StringRelatedField(source='plan.plan_type', read_only=True)
    onboarding_type = serializers.StringRelatedField(source='plan.onboarding_type', read_only=True)
    plan = serializers.PrimaryKeyRelatedField(read_only=True)
    plan_name = serializers.ReadOnlyField(source='plan.name')
    display_name = serializers.SerializerMethodField()
    bt_status = serializers.ReadOnlyField(source='status')
    needs_payment_method = serializers.BooleanField(source='plan.plan_type.needs_payment_method')
    video_url = serializers.ReadOnlyField(source='plan.plan_key.video_url')
    has_article_recs = serializers.SerializerMethodField()

    def get_display_name(self, obj):
        """If enterprise plan or display_status is UI_ENTERPRISE_CANCELED: return org name.
        else return plan.display_name
        """
        if obj.plan.isEnterprise() and obj.plan.organization:
            return obj.plan.organization.name
        if obj.display_status == UserSubscription.UI_ENTERPRISE_CANCELED:
            # User removed from org and switched to a free plan. Need to get org from OrgMember
            qset = OrgMember.objects.filter(user=obj.user, removeDate__isnull=False).order_by('-removeDate')
            if qset.exists():
                return qset[0].organization.name
        return obj.plan.display_name

    def get_has_article_recs(self, obj):
        """Returns True if there exists at least one Plantag with non-zero value for num_recs
        for obj.plan
        """
        qs = Plantag.objects.filter(plan=obj.plan, num_recs__gt=0)
        return qs.exists()

    class Meta:
        model = UserSubscription
        fields = (
            'id',
            'subscriptionId',
            'user',
            'plan',
            'plan_type',
            'onboarding_type',
            'plan_name',
            'display_name',
            'bt_status',
            'display_status',
            'billingCycle',
            'billingFirstDate',
            'billingStartDate',
            'billingEndDate',
            'needs_payment_method',
            'next_plan',
            'video_url',
            'has_article_recs',
            'created',
            'modified'
        )
        read_only_fields = fields



class InvitationDiscountReadSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='invitee.id', read_only=True)
    inviter = serializers.PrimaryKeyRelatedField(read_only=True)
    inviteeEmail = serializers.ReadOnlyField(source='invitee.email')
    inviteeFirstName = serializers.ReadOnlyField(source='invitee.profile.firstName')
    inviteeLastName = serializers.ReadOnlyField(source='invitee.profile.lastName')
    isComplete = serializers.SerializerMethodField()
    creditAmount = serializers.SerializerMethodField()

    def get_isComplete(self, obj):
        """Instance is complete if inviterDiscount is set
            (e.g. invitee begun Active subscription)
        """
        return obj.inviterDiscount is not None

    def get_creditAmount(self, obj):
        if obj.inviterDiscount and obj.creditEarned:
            return obj.inviterDiscount.amount
        return 0

    class Meta:
        model = InvitationDiscount
        fields = (
            'id',
            'inviter',
            'inviteeEmail',
            'inviteeFirstName',
            'inviteeLastName',
            'isComplete',
            'creditAmount',
            'created',
            'modified'
        )
        read_only_fields = fields

class UserEmailLookupSerializer(serializers.Serializer):
    email = serializers.EmailField()

class UserEmailUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def update(self, instance, validated_data):
        """This expects extra keys in the validated_data:
            apiConn: Auth0Api instance
        1. Set user with a new email
        2. Mark profile as not verified again
        3. Update Auth0 record with a new email that will trigger email verification
        Returns: User model instance
        """
        apiConn = validated_data['apiConn']
        # check email
        email = validated_data.get('email')
        user = instance
        profile = user.profile
        if email != user.email:
            logger.info('Update User record: change email from {0.email} to {1}'.format(user, email))
            # update user instance
            user.username = email; user.email = email
            user.save()
            # update profile as new email needs verification
            profile.verified = False
            profile.save(update_fields=('verified','modified'))
            # update auth0
            response = apiConn.updateUser(profile.socialId, email, True)
            logger.info('Auth0 User update result: {}'.format(response))
        return user
