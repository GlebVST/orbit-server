from __future__ import unicode_literals
import logging
import braintree
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.backends import RemoteUserBackend
from django.db import transaction
from django.utils import timezone
from .models import (
        AuthImpersonation,
        Profile,
        Customer,
        CmeTag,
        AffiliateDetail,
        SubscriptionPlan,
        Plantag,
        UserSubscription,
        OrbitCmeOffer,
        RecAllowedUrl,
        Organization,
        OrgMember
    )
logger = logging.getLogger('gen.auth')

#
# Format of user_id: {identity provider id}|{unique id in the provider}
# Reference: https://auth0.com/docs/user-profile/normalized
#
USER_BACKEND = 'users.auth_backends.Auth0Backend'
def configure_user(user_info_dict):
    """Called by auth_views.signup
    1. It updates the user.email/username to the email given in user_info_dict.
    2. It creates Profile instance for the user and completes the user initialization.
    Note: cannot make this a method of Auth0Backend because it expects extra data
        that is provided by auth_view.signup
    Args:
        user_info_dict: dict w. keys:
            user_id: auth0Id
            email: str (got from auth0_users using access_token)
            planId: str (valid plan.planid from SubscriptionPlan)
            inviterId: optional for signup. inviteId of an existing user.
            affiliateId: optional for signup. affiliateId of an AffiliateDetail.
    Returns: User instance or None
    """
    # required keys
    auth0Id = user_info_dict['user_id']
    planId = user_info_dict['planId']
    email = user_info_dict['email']
    # optional keys for signup
    inviterId = user_info_dict.get('inviterId', None)
    affiliateId = user_info_dict.get('affiliateId', '')
    if affiliateId is None: # cast None to '' to prevent not-null error when saving profile
        affiliateId = ''

    try:
        user = User.objects.get(username=auth0Id)
    except User.DoesNotExist:
        # authenticate failed to create this user
        return None
    plan = SubscriptionPlan.objects.get(planId=planId)
    inviter = None # if set, must be a User instance
    try:
        if affiliateId:
            qset = AffiliateDetail.objects.filter(affiliateId=affiliateId)
            if qset.exists():
                logger.info('User {0} was converted by affiliateId: {1}'.format(email, affiliateId))
                inviter = qset[0].affiliate.user # User instance (from Affiliate instance)
            else:
                logger.warning('Invalid affiliateId: {0}'.format(affiliateId))
        elif inviterId:
            qset = Profile.objects.filter(inviteId=inviterId)
            if qset.exists():
                inviter = qset[0].user # inviter User
                logger.info('User {0} was invited by {1.email}'.format(email, inviter))
            else:
                logger.warning('Invalid inviterId: {0}'.format(inviterId))
    except Exception as e:
        logger.exception('Failed to get inviter')
        inviter = None
    
    # Update user and create Profile
    with transaction.atomic():
        # Update user
        user.email = email
        user.username = email
        user.save()
        user.backend = USER_BACKEND
        profile = Profile.objects.createProfile(user, auth0Id, planId)
    if inviter:
        profile.inviter = inviter 
        profile.affiliateId = affiliateId
        profile.save(update_fields=('inviter','affiliateId'))
        
    # after saving profile instance, can add m2m rows
    profile.initializeFromPlanKey(plan.plan_key)
    
    # initialize UserCmeCredit instance for this user
    UserSubscription.objects.setUserCmeCreditByPlan(user, plan)
    # pre-generate offer for the welcome article
    OrbitCmeOffer.objects.makeWelcomeOffer(user)
    # Some plans provide article recs for specific tags
    plantags = Plantag.objects.filter(plan=plan, num_recs__gt=0)
    for pt in plantags:
        nc = RecAllowedUrl.objects.createRecsForNewIndivUser(user, pt.tag, pt.num_recs)
    # Does user match any Org based on email_domain?
    org_match = Organization.objects.getOrgForEmail(user.email)
    if org_match:
        orgm = OrgMember.objects.createMember(org_match, None, profile, indiv_subscriber=True)
    
    # create local customer object
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
    except:
        logger.exception('braintree.Customer.create exception')
    return user

class Auth0Backend(RemoteUserBackend):
    def authenticate(self, request, remote_user):
        """Args:
            request: request object or None 
            remote_user: dict with keys:
                user_id: auth0Id (which we store in Profile.socialId) *required*
            Returns: User instance or None
        """
        if 'user_id' not in remote_user: # required key for both login/signup
            return None
        auth0Id = remote_user['user_id']
        try:
            profile = Profile.objects.get(socialId=auth0Id)
        except Profile.DoesNotExist:
            # Create User instance as username=auth0Id
            # auth_views must call configure_user to update this user instance
            # and complete the initialization
            user = User.objects.create(username=auth0Id)
            user.backend = USER_BACKEND
        else:
            user = profile.user
            user.backend = USER_BACKEND
        return user

    def get_user(self, user_id):
        """Primary key identifier"""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None


class ImpersonateBackend(object):
    def authenticate(self, request, remote_user):
        if 'user_id' not in remote_user:
            return None
        auth0Id = remote_user['user_id']
        try:
            profile = Profile.objects.get(socialId=auth0Id)
        except Profile.DoesNotExist:
            return None
        else:
            user = profile.user
            # User must have is_staff perm to use impersonate
            if not user.is_staff:
                return None
        user.backend = USER_BACKEND
        # check AuthImpersonation
        now = timezone.now()
        qset = AuthImpersonation.objects.filter(impersonator=user, expireDate__gt=now, valid=True).order_by('-expireDate')
        if not qset.exists():
            return None
        m = qset[0]
        logger.info(m)
        return m.impersonatee

    def get_user(self, user_id):
        """Primary key identifier"""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
