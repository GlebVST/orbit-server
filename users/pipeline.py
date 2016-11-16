from django.contrib.auth.models import User
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
        # TODO: call braintree Customer create
