from django.contrib.auth.models import User
import braintree
from pprint import pprint
from .models import Profile, Customer

def save_profile(backend, user, response, *args, **kwargs):
    """Save Profile and Customer models for the user"""
    #pprint(response)
    qset = Profile.objects.filter(user=user)
    if not qset.exists():
        profile = Profile(user=user)
        profile.firstName = response.get('first_name', '')
        profile.lastName = response.get('last_name', '')
        profile.inviteId = "{0:%y%m%d}-{1:0>5}".format(user.date_joined, user.pk)
        if 'link' in response:
            profile.socialUrl = response['link']
    else:
        profile = qset[0]
        if not profile.firstName:
            profile.firstName = response.get('first_name', '')
        if not profile.lastName:
            profile.lastName = response.get('last_name', '')
        if not profile.socialUrl and 'link' in response:
            profile.socialUrl = response['link']
    profile.save()
    qset = Customer.objects.filter(user=user)
    if not qset.exists():
        customer = Customer(user=user)
        customer.balance = 100
        customer.save()
        # create braintree Customer
        result = braintree.Customer.create({
            "id": str(customer.customerId),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email
        })
        if not result.is_success:
            print('Create btCustomer failed.')
            # send email to admins...
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
                print('Create btCustomer failed.')
                # send email to admins...
        else:
            pass
