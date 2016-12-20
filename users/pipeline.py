import logging
from pprint import pprint

import braintree

from .models import Profile, Customer

logger = logging.getLogger(__name__)

def save_profile(backend, user, response, *args, **kwargs):
    """Save Profile and Customer models for the user"""
    pprint(response)
    qset = Profile.objects.filter(user=user)
    if not qset.exists():
        profile = Profile(user=user)
        profile.firstName = response.get('first_name', '')
        profile.lastName = response.get('last_name', '')
        profile.socialId = response.get('id', '')
        profile.inviteId = "{0:%y%m%d}-{1:0>5}".format(user.date_joined, user.pk)
        # copy social-auth email if it is a gmail address
        sa_email = response.get('email', '').lower()
        if sa_email.endswith('gmail.com'):
            profile.contactEmail = sa_email
        profile.save()
    else:
        profile = qset[0]
        changed = False
        if not profile.firstName:
            profile.firstName = response.get('first_name', '')
            changed = True
        if not profile.lastName:
            profile.lastName = response.get('last_name', '')
            changed = True
        profile.socialId = response.get('id', profile.socialId)
        changed = True
        #if not profile.socialId and 'id' in response:
        #    profile.socialId = response['id']
        #    changed = True
        if changed:
            profile.save()
    qset = Customer.objects.filter(user=user)
    if not qset.exists():
        customer = Customer(user=user)
        customer.balance = 100
        customer.save()
        result = None
        try:
            # create braintree Customer
            result = braintree.Customer.create({
                "id": str(customer.customerId),
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email
            })
        except Exception as ex:
            logger.error('Braintree error when trying to create customer: %s', ex, exc_info=ex)
        if not result or not result.is_success:
            print('Create braintree Customer failed.')
            # send email to admins...
            #todo prefer logging at ERROR level that could be later captured by email logger
    else:
        customer = qset[0]
        # if braintree Customer does not exist, then create it
        try:
            bt_customer = braintree.Customer.find(str(customer.customerId))
        except braintree.exceptions.not_found_error.NotFoundError:
            # create braintree Customer
            result = braintree.Customer.create({
                "id": str(customer.customerId),
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email
            })
            if not result.is_success:
                print('Create braintree Customer failed.')
                # send email to admins...
                #todo prefer logging at ERROR level that could be later captured by email logger
        except Exception as ex:
            logger.error('Braintree error when trying to find customer: %s', ex, exc_info=ex)
        else:
            pass
