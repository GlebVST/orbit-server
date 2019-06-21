from datetime import timedelta
from decimal import Decimal
from cStringIO import StringIO
from hashids import Hashids
import os
import braintree
import hashlib
import logging
import mimetypes
from smtplib import SMTPException
from django.conf import settings
from django.contrib.auth.models import User, Group
from django.utils import timezone
from rest_framework import serializers
from common.viewutils import newUuid, md5_uploaded_file
from common.appconstants import GROUP_ENTERPRISE_ADMIN, GROUP_ENTERPRISE_MEMBER
from common.signals import profile_saved
from .models import *
from .emailutils import sendPasswordTicketEmail
from .serializers import NestedHospitalSerializer, NestedResidencySerializer

logger = logging.getLogger('gen.esrl')

class OrgGroupSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=100)

    class Meta:
        model = OrgGroup
        fields = (
            'id',
            'name',
        )

    def create(self, validated_data):
        org = validated_data['organization']
        name = validated_data['name'].strip()
        instance = OrgGroup.objects.create(organization=org, name=name)
        return instance

class OrgMemberReadSerializer(serializers.ModelSerializer):
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    group = serializers.PrimaryKeyRelatedField(read_only=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    pending = serializers.ReadOnlyField()
    inviteDate = serializers.ReadOnlyField()
    degree = serializers.SerializerMethodField()
    joined = serializers.SerializerMethodField()
    groupName = serializers.SerializerMethodField()
    includeGroupInStats = serializers.SerializerMethodField()
    setPasswordEmailSent = serializers.ReadOnlyField()
    cmeRedeemed30 = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, read_only=True)
    # profile fields
    email = serializers.ReadOnlyField(source='user.email')
    firstName = serializers.ReadOnlyField(source='user.profile.firstName')
    lastName = serializers.ReadOnlyField(source='user.profile.lastName')

    def get_degree(self, obj):
        return obj.user.profile.formatDegrees()

    def get_joined(self, obj):
        return (obj.user.profile.verified and not obj.pending)

    def get_groupName(self, obj):
        if obj.group:
            return obj.group.name
        return ''

    def get_includeGroupInStats(self, obj):
        if obj.group:
            return obj.group.include_in_reports
        return False

    class Meta:
        model = OrgMember
        fields = (
            'id',
            'organization',
            'group',
            'groupName',
            'includeGroupInStats',
            'user',
            'pending',
            'degree',
            'is_admin',
            'compliance',
            'inviteDate',
            'removeDate',
            'joined',
            'snapshot',
            'snapshotDate',
            'numArticlesRead30',
            'cmeRedeemed30',
            'setPasswordEmailSent',
            'created',
            'modified',
            # profile fields
            'firstName',
            'lastName',
            'email',
        )
        read_only_fields = fields


class OrgMemberDetailSerializer(serializers.ModelSerializer):
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    group = serializers.PrimaryKeyRelatedField(read_only=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    pending = serializers.ReadOnlyField()
    inviteDate = serializers.ReadOnlyField()
    degree = serializers.SerializerMethodField()
    joined = serializers.SerializerMethodField()
    groupName = serializers.SerializerMethodField()
    setPasswordEmailSent = serializers.ReadOnlyField()
    cmeRedeemed30 = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, read_only=True)
    # extended profile fields
    email = serializers.ReadOnlyField(source='user.email')
    firstName = serializers.ReadOnlyField(source='user.profile.firstName')
    lastName = serializers.ReadOnlyField(source='user.profile.lastName')
    birthDate = serializers.ReadOnlyField(source='user.profile.birthDate')
    npiNumber = serializers.ReadOnlyField(source='user.profile.npiNumber')
    country = serializers.PrimaryKeyRelatedField(source='user.profile.country', read_only=True)
    residencyEndDate = serializers.ReadOnlyField(source='user.profile.residencyEndDate')
    residency_program = serializers.SerializerMethodField()
    degrees = serializers.PrimaryKeyRelatedField(source='user.profile.degrees',
            many=True, read_only=True)
    specialties = serializers.PrimaryKeyRelatedField(source='user.profile.specialties',
            many=True, read_only=True)
    subspecialties = serializers.PrimaryKeyRelatedField(source='user.profile.subspecialties',
            many=True, read_only=True)
    hospitals = NestedHospitalSerializer(source='user.profile.hospitals',
            many=True, read_only=True)

    def get_degree(self, obj):
        return obj.user.profile.formatDegrees()

    def get_joined(self, obj):
        return (obj.user.profile.verified and not obj.pending)

    def get_groupName(self, obj):
        if obj.group:
            return obj.group.name
        return ''

    def get_residency_program(self, obj):
        profile = obj.user.profile
        if profile.residency_program:
            s = NestedResidencySerializer(profile.residency_program)
            return s.data
        return None

    class Meta:
        model = OrgMember
        fields = (
            'id',
            'organization',
            'group',
            'groupName',
            'user',
            'pending',
            'degree',
            'is_admin',
            'compliance',
            'inviteDate',
            'removeDate',
            'joined',
            'snapshot',
            'snapshotDate',
            'numArticlesRead30',
            'cmeRedeemed30',
            'setPasswordEmailSent',
            'created',
            'modified',
            # profile fields
            'firstName',
            'lastName',
            'email',
            'country',
            'birthDate',
            'npiNumber',
            'residency_program',
            'residencyEndDate',
            'degrees',
            'specialties',
            'subspecialties',
            'hospitals',
        )
        read_only_fields = fields


class OrgMemberFormSerializer(serializers.Serializer):
    group = serializers.PrimaryKeyRelatedField(
        queryset=OrgGroup.objects.all(),
        allow_null=True
    )
    is_admin = serializers.BooleanField()
    password_ticket = serializers.BooleanField(required=False, default=True)
    firstName = serializers.CharField(max_length=30)
    lastName = serializers.CharField(max_length=30)
    npiNumber = serializers.CharField(max_length=20, allow_blank=True)
    email = serializers.EmailField()
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
        many=True,
    )
    hospitals = serializers.PrimaryKeyRelatedField(
        queryset=Hospital.objects.all(),
        many=True
    )

    def create(self, validated_data):
        """This expects extra keys in the validated_data:
            apiConn: Auth0Api instance
            organization: Organization instance
            plan: SubscriptionPlan instance whose plan_type is ENTERPRISE
        1. Create Auth0 user account
        2. Create User & Profile instance (and assign org)
        3. Create local and BT Customer object for user.
        4. Create UserSubscription using plan_type=ENTERPRISE
        5. Create OrgAdmin model instance
        6. Assign groups to the new user
        7. Generate change-password-ticket if given
        Returns: OrgMember model instance
        """
        apiConn = validated_data['apiConn']
        org = validated_data['organization']
        group = validated_data['group']
        plan = validated_data['plan']
        firstName = validated_data['firstName'].strip()
        lastName = validated_data['lastName'].strip()
        email = validated_data['email']
        is_admin = validated_data.get('is_admin', False)
        password_ticket = validated_data.get('password_ticket', True)
        country_usa = Country.objects.get(code=Country.USA)
        # 1. get or create auth0 user
        socialId = apiConn.findUserByEmail(email)
        if not socialId:
            now = timezone.now()
            passw = apiConn.make_initial_pass(email, now)
            socialId = apiConn.createUser(email, passw)
        # 2. create user and profile instances
        profile = Profile.objects.createUserAndProfile(
            email,
            planId=plan.planId,
            socialId=socialId,
            organization=org,
            firstName=firstName,
            lastName=lastName
            )
        profile.country = country_usa
        profile.save(update_fields=('country',))
        user = profile.user
        # 3. create local and BT Customer object
        customer = Customer(user=user)
        customer.save()
        try:
            # create braintree Customer
            result = braintree.Customer.create({
                "id": str(customer.customerId),
                "email": user.email
            })
            if not result.is_success:
                logger.error('braintree.Customer.create failed. Result message: {0.message}'.format(result))
                return None
        except:
            logger.exception('braintree.Customer.create exception')
        # 4. Create Enterprise UserSubscription for user
        user_subs = UserSubscription.objects.createEnterpriseMemberSubscription(user, plan)
        # 5. create OrgMember instance
        m = OrgMember.objects.createMember(org, group, profile, is_admin)
        # 6. Assign extra groups
        if is_admin:
            user.groups.add(Group.objects.get(name=GROUP_ENTERPRISE_ADMIN))
            user.groups.remove(Group.objects.get(name=GROUP_ENTERPRISE_MEMBER))
            # admin users don't need to be forced to welcome/plugin sequence
            profile.accessedTour = True
            profile.save(update_fields=('accessedTour',))
        else:
            # pre-generate a first orbit cme offer for the welcome article
            OrbitCmeOffer.objects.makeWelcomeOffer(user)
        # 7. Create change-password ticket
        if password_ticket:
            m = OrgMember.objects.sendPasswordTicket(socialId, m, apiConn)
        return m


    def update(self, instance, validated_data):
        """This expects extra keys in the validated_data:
            apiConn: Auth0Api instance
        Update OrgMember model instance. If user is removed, then UserSubscription
            manager method is called to end current user_subs.
        Note: UI only displays active users, hence from UI, update can only set
            removeDate (but not clear it). The ent. admin must re-add the user
            using the create form.
        Returns: OrgMember model instance
        """
        user = instance.user
        profile = user.profile
        apiConn = validated_data['apiConn']
        group = validated_data.get('group', instance.group)
        firstName = validated_data.get('firstName', profile.firstName)
        lastName = validated_data.get('lastName', profile.lastName)
        email = validated_data.get('email', user.email)
        is_admin = validated_data.get('is_admin', instance.is_admin)
        password_ticket = validated_data.get('password_ticket', True)
        # check email
        if email != user.email:
            logger.info('UpdateOrgMember: change email from {0.email} to {1}'.format(user, email))
            # update user instance
            user.username = email; user.email = email
            user.save()
            # update auth0
            verify_email = password_ticket # if True, auth0 will send verification email
            response = apiConn.updateUser(profile.socialId, email, verify_email)
        # check if update firstName/lastName
        if firstName != profile.firstName or lastName != profile.lastName:
            profile.firstName = firstName
            profile.lastName = lastName
            profile.save(update_fields=('firstName','lastName'))
            instance.fullname = OrgMember.objects.makeFullName(firstName, lastName)
        # update OrgMember and user groups
        if group != instance.group:
            instance.group = group
        if is_admin != instance.is_admin:
            instance.is_admin = is_admin
            ga = Group.objects.get(name=GROUP_ENTERPRISE_ADMIN)
            gm = Group.objects.get(name=GROUP_ENTERPRISE_MEMBER)
            if is_admin:
                user.groups.add(ga)
                user.groups.remove(gm)
                logger.info('UpdateOrgMember: switch user {0.pk}|{0} from provider to admin'.format(user))
                ugs = user.usergoals.all()
                if ugs.exists():
                    ugs.delete()
            else:
                user.groups.remove(ga)
                user.groups.add(gm)
                logger.info('UpdateOrgMember: switch user {0.pk}|{0} from admin to provider.'.format(user))
        instance.save()
        return instance


class OrgFileReadSerializer(serializers.ModelSerializer):
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    url = serializers.FileField(source='document', max_length=None, allow_empty_file=False, use_url=True)

    class Meta:
        model = OrgFile
        fields = (
            'id',
            'organization',
            'user',
            'name',
            'url',
            'content_type',
            'created',
        )
        read_only_fields = fields


class OrbitCmeOfferAggSerializer(serializers.ModelSerializer):
    value = serializers.IntegerField(source='offers')
    class Meta:
        model = OrbitCmeOfferAgg
        fields = (
            'day',
            'value'
        )
        read_only_fields = fields


class OrgAggSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrgAgg
        fields = (
            'id',
            'day',
            'users_active',
            'users_inactive',
            'users_invited',
            'licenses_expired',
            'licenses_expiring',
            'cme_gap_expired',
            'cme_gap_expiring'
        )
        read_only_fields = fields
