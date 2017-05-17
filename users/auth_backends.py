from __future__ import unicode_literals
import logging
import braintree
from hashids import Hashids
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from .models import Profile, Customer

logger = logging.getLogger('gen.auth')

# https://auth0.com/docs/user-profile/normalized
# format of user_id: {identity provider id}|{unique id in the provider}

# https://docs.djangoproject.com/en/1.10/topics/auth/customizing/
class Auth0Backend(object):
    def authenticate(self, user_info):
        # check if this is an Auth0 authentication attempt
        if 'user_id' not in user_info or 'email' not in user_info:
            return None
        user_id = user_info['user_id']
        email = user_info['email']
        email_verified = user_info.get('email_verified', False)
        picture = user_info.get('picture', '')
        try:
            user = User.objects.get(username=email) # the unique constraint is on the username field in the users table
        except User.DoesNotExist:
            with transaction.atomic():
                user = User.objects.create(
                    username=email,
                    email=email
                )
                profile = Profile(user=user)
                profile.socialId = user_id
                hashgen = Hashids(salt=settings.HASHIDS_SALT, min_length=10)
                profile.inviteId = hashgen.encode(user.pk)
                if picture:
                    profile.pictureUrl = picture
                profile.verified = email_verified
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
            if email_verified != profile.verified:
                profile.verified = email_verified
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
