import logging
from urlparse import urlparse, urldefrag
from rest_framework import serializers
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

class CmeTagWithSpecSerializer(serializers.ModelSerializer):
    specialties = serializers.PrimaryKeyRelatedField(
        queryset=PracticeSpecialty.objects.all(),
        many=True
    )
    class Meta:
        model = CmeTag
        fields = ('id', 'name', 'priority', 'description', 'specialties')

class CmeTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = CmeTag
        fields = ('id', 'name', 'priority', 'description')

# Used by auth_view to serialize the SA-CME tag
class ActiveCmeTagSerializer(serializers.ModelSerializer):
    is_active = serializers.SerializerMethodField()

    def get_is_active(self, obj):
        return True

    class Meta:
        model = CmeTag
        fields = ('id', 'name', 'priority', 'description', 'is_active')


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

    class Meta:
        model = ProfileCmetag
        fields = ('id', 'name', 'priority', 'description', 'is_active')

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
                logger.warning('ManageProfileCmeTags: Invalid tag for user {0}: {1}'.format(user, t))
            else:
                if pct.is_active != is_active:
                    pct.is_active = is_active
                    pct.save()
                    logger.info('Updated ProfileCmetag {0}'.format(pct))
        # emit profile_saved signal
        ret = profile_saved.send(sender=instance.__class__, user_id=user.pk)
        return instance

class ProfileUpdateSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        allow_null=True
    )
    residency = serializers.PrimaryKeyRelatedField(
        queryset=Hospital.objects.all(),
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
    hospitals = serializers.PrimaryKeyRelatedField(
        queryset=Hospital.objects.all(),
        many=True
    )
    cmeTags = serializers.SerializerMethodField()
    isSignupComplete = serializers.SerializerMethodField()
    isNPIComplete = serializers.SerializerMethodField()
    profileComplete = serializers.SerializerMethodField()

    def get_isSignupComplete(self, obj):
        return obj.isSignupComplete()

    def get_isNPIComplete(self, obj):
        return obj.isNPIComplete()

    def get_profileComplete(self, obj):
        return obj.measureComplete()

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
            'residency',
            'birthDate',
            'residencyEndDate',
            'affiliationText',
            'interestText',
            'planId',
            'inviteId',
            'socialId',
            'pictureUrl',
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
            'hospitals',
            'verified',
            'accessedTour',
            'cmeStartDate',
            'cmeEndDate',
            'isNPIComplete',
            'isSignupComplete',
            'profileComplete',
            'created',
            'modified'
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
            'created',
            'modified'
        )

    def update(self, instance, validated_data):
        """
        If any new specialties added, then check for new cmeTags.
        If a specialty is removed, then remove its cmeTags if not assigned to
            any entry made by the user.
        Emit profile_saved signal at the end.
        """
        user = instance.user
        upd_cmetags = False
        tag_ids = None
        # get current specialties before updating the instance
        curSpecs = set([ps for ps in instance.specialties.all()])
        # update the instance
        instance = super(ProfileUpdateSerializer, self).update(instance, validated_data)
        # now handle cmeTags
        spec_key = 'specialties'
        if spec_key in validated_data:
            # need to check if key exists, because a PATCH request may not contain the spec_key
            pracSpecs = validated_data[spec_key]
            newSpecs = set([ps for ps in pracSpecs])
            newly_added_specs = newSpecs.difference(curSpecs)
            del_specs = curSpecs.difference(newSpecs)
            for ps in del_specs:
                logger.info('User {0.email} : remove ps: {1.name}'.format(user, ps))
                for t in ps.cmeTags.all():
                    pct_qset = ProfileCmetag.objects.filter(profile=instance, tag=t)
                    if pct_qset.exists():
                        pct = pct_qset[0]
                        num_entries = t.entries.filter(user=user).count()
                        #logger.debug('Num entries for tag {0} = {1}'.format(t, num_entries))
                        if num_entries == 0:
                            pct.delete()
                            logger.info('Delete unused ProfileCmetag: {0}'.format(pct))
                        elif pct.is_active:
                            # Set is_active to false
                            pct.is_active = False
                            pct.save()
                            logger.info('Inactivate ProfileCmetag: {0}'.format(pct))
            # get refreshed set
            tag_ids = set([t.pk for t in instance.cmeTags.all()])
            for ps in newly_added_specs:
                logger.info('User {0.email} : Add ps: {1.name}'.format(user, ps))
                for t in ps.cmeTags.all():
                    # tag may already exist from a previous occasion in which ps was assigned to user
                    pct, created = ProfileCmetag.objects.get_or_create(profile=instance, tag=t)
                    if created:
                        logger.info('New ProfileCmetag: {0}'.format(pct))
                    elif not pct.is_active:
                        pct.is_active = True
                        pct.save()
                        logger.info('Re-activate ProfileCmetag: {0}'.format(pct))
        # emit profile_saved signal
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
    isSignupComplete = serializers.SerializerMethodField()
    isNPIComplete = serializers.SerializerMethodField()
    profileComplete = serializers.SerializerMethodField()
    cmeTags = serializers.SerializerMethodField()
    residency = serializers.SerializerMethodField()

    def get_isSignupComplete(self, obj):
        return obj.isSignupComplete()

    def get_isNPIComplete(self, obj):
        return obj.isNPIComplete()

    def get_profileComplete(self, obj):
        return obj.measureComplete()

    def get_cmeTags(self, obj):
        qset = ProfileCmetag.objects.filter(profile=obj)
        return [ProfileCmetagSerializer(m).data for m in qset]

    def get_residency(self, obj):
        if obj.residency:
            s = NestedHospitalSerializer(obj.residency)
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
            'residency',
            'birthDate',
            'residencyEndDate',
            'affiliationText',
            'interestText',
            'planId',
            'inviteId',
            'socialId',
            'pictureUrl',
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
            'hospitals',
            'verified',
            'accessedTour',
            'cmeStartDate',
            'cmeEndDate',
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
            allow_null=True
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
            'domain_name',
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
        netloc = res.netloc
        # create AllowedHost
        host, created = AllowedHost.objects.get_or_create(hostname=netloc)
        if created:
            logger.info('EligibleSite: new AllowedHost: {0}'.format(netloc))
        # create AllowedUrl
        allowed_url, created = AllowedUrl.objects.get_or_create(
            host=host,
            eligible_site=instance,
            url=example_url,
            page_title=validated_data.get('example_title')
        )
        if created:
            logger.info('EligibleSite: new AllowedUrl: {0.url}'.format(allowed_url))
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
    plan = serializers.PrimaryKeyRelatedField(read_only=True)
    plan_name = serializers.ReadOnlyField(source='plan.name')
    display_name = serializers.ReadOnlyField(source='plan.display_name')
    bt_status = serializers.ReadOnlyField(source='status')
    needs_payment_method = serializers.BooleanField(source='plan.plan_type.needs_payment_method')

    class Meta:
        model = UserSubscription
        fields = (
            'id',
            'subscriptionId',
            'user',
            'plan',
            'plan_type',
            'plan_name',
            'display_name',
            'bt_status',
            'display_status',
            'billingFirstDate',
            'billingStartDate',
            'billingEndDate',
            'needs_payment_method',
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
