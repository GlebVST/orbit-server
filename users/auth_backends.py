from __future__ import unicode_literals
import logging
import braintree
from hashids import Hashids
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from .models import Profile, Customer, Affiliate

logger = logging.getLogger('gen.auth')
HASHIDS_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890!@' # extend alphabet with ! and @
# https://auth0.com/docs/user-profile/normalized
# format of user_id: {identity provider id}|{unique id in the provider}

# https://docs.djangoproject.com/en/1.10/topics/auth/customizing/
# Notes from 1.11 release notes:
#  authenticate() now passes a request argument to the authenticate() method of authentication backends.
#  Support for methods that dont accept request as the first positional argument will be removed in Django 2.1.
class Auth0Backend(object):
    def authenticate(self, user_info):
        # check if this is an Auth0 authentication attempt
        if 'user_id' not in user_info or 'email' not in user_info:
            return None
        user_id = user_info['user_id']
        email = user_info['email']
        email_verified = user_info.get('email_verified', None)
        picture = user_info.get('picture', '')
        # optional keys passed by login_via_token
        inviterId = user_info.get('inviterId', None)
        affiliateId = user_info.get('affiliateId', None)
        try:
            user = User.objects.get(username=email) # the unique constraint is on the username field in the users table
        except User.DoesNotExist:
            hashgen = Hashids(salt=settings.HASHIDS_SALT, alphabet=HASHIDS_ALPHABET, min_length=5)
            with transaction.atomic():
                user = User.objects.create(
                    username=email,
                    email=email
                )
                profile = Profile(user=user)
                profile.socialId = user_id
                profile.inviteId = hashgen.encode(user.pk)
                if picture:
                    profile.pictureUrl = picture
                profile.verified = bool(email_verified)
                if affiliateId:
                    qset = Affiliate.objects.filter(affiliateId=affiliateId)
                    if qset.exists():
                        profile.inviter = qset[0].user # inviter User
                        logger.info('User {0.email} was converted by {1.email}'.format(user, profile.inviter))
                    else:
                        logger.warning('Invalid affiliateId: {0}'.format(affiliateId))
                elif inviterId:
                    qset = Profile.objects.filter(inviteId=inviterId)
                    if qset.exists():
                        profile.inviter = qset[0].user # inviter User
                        logger.info('User {0.email} was invited by {1.email}'.format(user, profile.inviter))
                    else:
                        logger.warning('Invalid inviterId: {0}'.format(inviterId))
                profile.save()
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
        else:
            profile = user.profile
            # profile.socialId must match user_id
            if profile.socialId != user_id:
                # We expect only one method of login (e.g. user/pass via auth0 provider), so only 1 socialId per user.
                # If this changes in the future, we need multiple socialIds per user.
                logger.warning('user_id {0} does not match profile.socialId: {1} for user email: {2}'.format(user_id, profile.socialId, user.email))
            saveProfile = False
            # Check update verified
            if email_verified is not None:
                ev = bool(email_verified)
                if ev != profile.verified:
                    profile.verified = ev
                    logger.info('Update email_verified for {0}'.format(user_id))
                    saveProfile = True
            # Check update picture
            if picture and profile.pictureUrl != picture:
                profile.pictureUrl = picture
                saveProfile = True
            if saveProfile:
                profile.save()
        return user

    def get_user(self, user_id):
        """Primary key identifier"""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
