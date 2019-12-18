from __future__ import unicode_literals
import logging
import braintree
from django.conf import settings
from django.contrib.auth.models import User
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
        RecAllowedUrl
    )
logger = logging.getLogger('gen.auth')
# https://auth0.com/docs/user-profile/normalized
# format of user_id: {identity provider id}|{unique id in the provider}

class Auth0Backend(object):
    def authenticate(self, request, user_info):
        # check if this is an Auth0 authentication attempt
        if 'user_id' not in user_info or 'email' not in user_info:
            return None
        user_id = user_info['user_id']
        email = user_info['email']
        email_verified = user_info.get('email_verified', None)
        picture = user_info.get('picture', '')
        # optional keys passed by login_via_token
        inviterId = user_info.get('inviterId', None)
        affiliateId = user_info.get('affiliateId', '')
        if affiliateId is None: # cast None to '' to prevent not-null error when saving profile
            affiliateId = ''
        planId = user_info.get('planId', None) # required for new user creation (signup)
        try:
            user = User.objects.get(username__iexact=email) # the unique constraint is on the username field in the users table
        except User.DoesNotExist:
            if not planId:
                logger.error('New user signup error for {0}: planId was not provided.'.format(email))
                return None
            plan = SubscriptionPlan.objects.get(planId=planId)
            inviter = None
            with transaction.atomic():
                if affiliateId:
                    qset = AffiliateDetail.objects.filter(affiliateId=affiliateId)
                    if qset.exists():
                        inviter = qset[0].affiliate # Affiliate instance
                        logger.info('User {0} was converted by {1}'.format(email, affiliateId))
                    else:
                        logger.warning('Invalid affiliateId: {0}'.format(affiliateId))
                elif inviterId:
                    qset = Profile.objects.filter(inviteId=inviterId)
                    if qset.exists():
                        inviter = qset[0].user # inviter User
                        logger.info('User {0} was invited by {1.email}'.format(email, inviter))
                    else:
                        logger.warning('Invalid inviterId: {0}'.format(inviterId))
                # Create User and Profile instance
                profile = Profile.objects.createUserAndProfile(
                    email,
                    planId=planId,
                    inviter=inviter,
                    affiliateId=affiliateId,
                    socialId=user_id,
                    pictureUrl=picture,
                    verified=bool(email_verified)
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
        else:
            profile = user.profile
            # profile.socialId must match user_id
            if profile.socialId != user_id:
                # We expect only one method of login (e.g. user/pass via auth0 provider), so only 1 socialId per user.
                # If this changes in the future, we need multiple socialIds per user.
                logger.warning('user_id {0} does not match profile.socialId: {1} for user email: {2}'.format(user_id, profile.socialId, user.email))
            saveProfile = False
            # Check verified
            if email_verified is not None:
                ev = bool(email_verified)
                if ev != profile.verified:
                    profile.verified = ev
                    profile.save(update_fields=('verified',))
                    saveProfile = True
            # Check picture
            if picture and profile.pictureUrl != picture:
                profile.pictureUrl = picture
                profile.save(update_fields=('pictureUrl',))
        return user

    def get_user(self, user_id):
        """Primary key identifier"""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None


class ImpersonateBackend(object):
    def authenticate(self, request, user_info):
        if 'user_id' not in user_info or 'email' not in user_info:
            return None
        user_id = user_info['user_id']
        email = user_info['email']
        try:
            staff_user = User.objects.get(username=email) 
        except User.DoesNotExist:
            return None
        if not staff_user.is_staff:
            return None
        # check AuthImpersonation
        now = timezone.now()
        qset = AuthImpersonation.objects.filter(impersonator=staff_user, expireDate__gt=now, valid=True).order_by('-expireDate')
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

