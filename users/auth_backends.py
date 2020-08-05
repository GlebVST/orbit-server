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

# https://auth0.com/docs/user-profile/normalized
# format of user_id: {identity provider id}|{unique id in the provider}
class Auth0Backend(RemoteUserBackend):
    def authenticate(self, request, remote_user):
        """Args:
            request: request object or None 
            remote_user: dict with keys:
                user_id: auth0Id (which we store in Profile.socialId) *required*
                planId: expected for new user signup only, else we assume an
                    existing user is logging in
                email: expected for new user signup
                inviterId: optional for signup. inviteId of an existing user.
                affiliateId: optional for signup. affiliateId of an AffiliateDetail.
            Returns: User instance or None
        """
        if 'user_id' not in remote_user: # required key for both login/signup
            return None
        auth0Id = remote_user['user_id']
        if 'planId' not in remote_user:
            # We expect this is an existing user login
            try:
                profile = Profile.objects.get(socialId=auth0Id)
            except Profile.DoesNotExist:
                return None
            else:
                user = profile.user
                user.backend = 'users.auth_backends.Auth0Backend'
                return user
        # Else: this is a new user signup.
        if 'email' not in remote_user: # required key for signup
            logger.warning('New user signup error for {user_id}: email was not provided.'.format(**remote_user))
            return None
        # username and email are equivalent b/c we only ask for email during signup
        username = remote_user['email']
        try:
            user = User.objects.get(username__iexact=username) # the unique constraint is on the username field in the users table
        except User.DoesNotExist:
            # New user signup
            # required keys in remote_user for signup
            planId = remote_user.get('planId', None) # planId for the user-select subscription plan
            if not planId:
                logger.warning('New user signup error for {0}: planId was not provided.'.format(username))
                return None
            # optional keys passed by signup
            inviterId = remote_user.get('inviterId', None)
            affiliateId = remote_user.get('affiliateId', '')
            if affiliateId is None: # cast None to '' to prevent not-null error when saving profile
                affiliateId = ''
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
            with transaction.atomic():
                # Create User and Profile instance
                profile = Profile.objects.createUserAndProfile(
                    email,
                    planId=planId,
                    inviter=inviter, # User instance or None
                    affiliateId=affiliateId,
                    socialId=auth0Id,
                )
                # after saving profile instance, can add m2m rows
                profile.initializeFromPlanKey(plan.plan_key)
                # create local customer object
                user = profile.user
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
        else:
            logger.warning('Signup: user already exists: {0.pk}|{0}'.format(user))
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
        user.backend = 'users.auth_backends.Auth0Backend'
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
