from datetime import timedelta
from decimal import Decimal
from cStringIO import StringIO
from hashids import Hashids
import os
import hashlib
import logging
import mimetypes
from django.contrib.auth.models import User, Group
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework import serializers
from common.viewutils import newUuid, md5_uploaded_file
from common.appconstants import GROUP_ENTERPRISE_ADMIN, GROUP_ENTERPRISE_MEMBER
from .models import *
from goals.models import UserGoal
from pprint import pprint

logger = logging.getLogger('gen.esrl')

class OrgMemberReadSerializer(serializers.ModelSerializer):
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    is_admin = serializers.ReadOnlyField()
    compliance = serializers.ReadOnlyField()
    removeDate = serializers.ReadOnlyField()
    email = serializers.ReadOnlyField(source='user.email')
    firstName = serializers.ReadOnlyField(source='user.profile.firstName')
    lastName = serializers.ReadOnlyField(source='user.profile.lastName')
    verified = serializers.ReadOnlyField(source='user.profile.verified')
    degree = serializers.SerializerMethodField()

    def get_degree(self, obj):
        return obj.user.profile.formatDegrees()

    class Meta:
        model = OrgMember
        fields = (
            'id',
            'organization',
            'user',
            'firstName',
            'lastName',
            'email',
            'degree',
            'is_admin',
            'compliance',
            'removeDate',
            'verified',
            'created',
            'modified'
        )

class OrgMemberFormSerializer(serializers.Serializer):
    firstName = serializers.CharField(max_length=30)
    lastName = serializers.CharField(max_length=30)
    email = serializers.EmailField()
    degrees = serializers.PrimaryKeyRelatedField(
        queryset=Degree.objects.all(),
        many=True
    )
    removeDate = serializers.DateTimeField(required=False, allow_null=True)
    is_admin = serializers.BooleanField(required=False, default=False)
    verify_email = serializers.BooleanField(required=False, default=True)

    def create(self, validated_data):
        """This expects extra keys in the validated_data:
            authApi: Auth0Api instance
            organization: Organization instance
        1. Create Auth0 user account
        2. Create User & Profile instance (and assign org)
        3. Create UserSubscription using plan_type=ENTERPRISE
        4. Create OrgAdmin model instance
        Returns: OrgAdmin model instance
        """
        apiConn = validated_data['apiConn']
        org = validated_data['organization']
        firstName = validated_data['firstName'].strip()
        lastName = validated_data['lastName'].strip()
        email = validated_data['email']
        degrees = validated_data['degrees']
        is_admin = validated_data.get('is_admin', False)
        verify_email = validated_data.get('verify_email', True)
        # 0. get Enterprise Plan
        plan = SubscriptionPlan.objects.getEnterprisePlan()
        # 1. get or create auth0 user
        socialId = apiConn.findUserByEmail(email)
        if not socialId:
            now = timezone.now()
            passw = apiConn.make_initial_pass(email, now.year)
            socialId = apiConn.createUser(email, passw, verify_email)
        logger.debug('socialId: {0}'.format(socialId))
        # 2. create user and profile instances
        profile = Profile.objects.createUserAndProfile(
            email,
            planId=plan.planId,
            socialId=socialId,
            organization=org,
            firstName=firstName,
            lastName=lastName
            )
        if degrees:
            profile.degrees.set(degrees)
        user = profile.user
        # 3. Create Enterprise UserSubscription for user
        user_subs = UserSubscription.objects.createEnterpriseMemberSubscription(user, plan)
        # 4. create OrgMember instance
        m = OrgMember.objects.createMember(org, profile, is_admin)
        # 5. Assign groups
        user.groups.add(Group.objects.get(name=GROUP_ENTERPRISE_MEMBER))
        if is_admin:
            user.groups.add(Group.objects.get(name=GROUP_ENTERPRISE_ADMIN))
        return m


    def update(self, instance, validated_data):
        """This expects extra keys in the validated_data:
            apiConn: Auth0Api instance
        Update OrgAdmin model instance
        Returns: OrgAdmin model instance
        """
        user = instance.user
        profile = user.profile
        apiConn = validated_data['apiConn']
        firstName = validated_data.get('firstName', profile.firstName)
        lastName = validated_data.get('lastName', profile.lastName)
        email = validated_data.get('email', user.email)
        is_admin = validated_data.get('is_admin', instance.is_admin)
        removeDate = validated_data.get('removeDate', instance.removeDate)
        verify_email = validated_data.get('verify_email', True)
        # check email
        if email != user.email:
            logger.info('UpdateOrgMember: change email from {0.email} to {1}'.format(user, email))
            # update user instance
            user.username = email; user.email = email
            user.save()
            # update auth0
            response = apiConn.updateUser(user.profile.socialId, email, verify_email)
        # update profile
        if firstName != profile.firstName or lastName != profile.lastName:
            profile.firstName = firstName
            profile.lastName = lastName
            profile.save(update_fields=('firstName','lastName'))
            instance.fullname = OrgMember.objects.makeFullName(firstName, lastName)
        # update primary role aka degrees
        if 'degrees' in validated_data:
            vdegs = validated_data['degrees']
            newDeg = vdegs[0]
            curDeg = profile.degrees.all()[0] if profile.degrees.exists() else None
            if vdegs:
                profile.degrees.set(vdegs)
            if newDeg != curDeg:
                logger.info('UpdateOrgMember: change degree from {0} to {1} for user {2}'.format(curDeg, newDeg, user))
                # find and remove no-longer applicable goals
                ##UserGoal.rematchGoalsForProfile(user)
        # update OrgMember and user groups
        if removeDate != instance.removeDate:
            instance.removeDate = removeDate
            logger.info('UpdateOrgMember: set removeDate to {0} for user {1}'.format(removeDate, user))
        if is_admin != instance.is_admin:
            instance.is_admin = is_admin
            ga = Group.objects.get(name=GROUP_ENTERPRISE_ADMIN)
            if is_admin:
                user.groups.add(ga)
            else:
                user.groups.remove(ga)
        instance.save()
        return instance
