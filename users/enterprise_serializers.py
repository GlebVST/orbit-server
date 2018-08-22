from datetime import timedelta
from decimal import Decimal
from cStringIO import StringIO
from hashids import Hashids
import os
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
from .emailutils import sendChangePasswordTicketEmail

logger = logging.getLogger('gen.esrl')

class OrgMemberReadSerializer(serializers.ModelSerializer):
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)
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
        read_only_fields = fields

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
    password_ticket = serializers.BooleanField(required=False, default=True)

    def create(self, validated_data):
        """This expects extra keys in the validated_data:
            apiConn: Auth0Api instance
            organization: Organization instance
        1. Create Auth0 user account
        2. Create User & Profile instance (and assign org)
        3. Create UserSubscription using plan_type=ENTERPRISE
        4. Create OrgAdmin model instance
        5. Assign groups to the new user
        6. Generate change-password-ticket if given
        Returns: OrgAdmin model instance
        """
        apiConn = validated_data['apiConn']
        org = validated_data['organization']
        firstName = validated_data['firstName'].strip()
        lastName = validated_data['lastName'].strip()
        email = validated_data['email']
        degrees = validated_data['degrees']
        is_admin = validated_data.get('is_admin', False)
        password_ticket = validated_data.get('password_ticket', True)
        # 0. get Enterprise Plan
        plan = SubscriptionPlan.objects.getEnterprisePlan()
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
        # 6. Create change-password ticket
        if password_ticket:
            redirect_url = 'https://{0}{1}'.format(settings.SERVER_HOSTNAME, settings.UI_LINK_LOGIN)
            ticket_url = apiConn.change_password_ticket(socialId, redirect_url)
            logger.debug(ticket_url)
            try:
                sendChangePasswordTicketEmail(m, ticket_url)
            except SMTPException as e:
                logger.warning('sendChangePasswordTicketEmail failed for user {0}. ticket_url={1}'.format(user, ticket_url))
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
                logger.info('UpdateOrgMember: User {0} change degree from {1} to {2}.'.format(user, curDeg, newDeg))
                # emit profile_saved signal
                ret = profile_saved.send(sender=instance.__class__, user_id=user.pk)
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
            'dialect',
            'content_type',
            'created',
            'modified'
        )
        read_only_fields = fields
