import os
import pytz
from users.models import *
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from common import viewutils
from random import randint


def getUser(firstName=None, lastName=None, email=None):
    filter_kwargs = {}
    if firstName:
        filter_kwargs['first_name'] = firstName
    if lastName:
        filter_kwargs['last_name'] = lastName
    if email:
        filter_kwargs['email'] = email
    if filter_kwargs:
        qset = User.objects.exclude(username='admin').filter(**filter_kwargs).order_by('-last_login')
        if qset.exists():
            return qset[0]
        else:
            print('User not found')
    else:
        print('User filter parameter is required.')

def makeOffers(user):
    NUM_OFFERS = 3
    sponsor = Sponsor.objects.get(pk=1)
    # the EligibleSites appropriate for this user
    esiteids = EligibleSite.objects.getSiteIdsForProfile(user.profile)
    # exclude urls for which user already has un-redeemed un-expired offers waiting to be redeemed
    now = timezone.now()
    exclude_urls = OrbitCmeOffer.objects.filter(
        user=user,
        redeemed=False,
        eligible_site__in=esiteids,
        expireDate__gte=now
    ).values_list('url', flat=True).distinct()
    print('Num exclude_urls: {0}'.format(len(exclude_urls)))
    aurls = AllowedUrl.objects.filter(valid=True, eligible_site__in=esiteids).exclude(pk__in=exclude_urls).order_by('?')[:NUM_OFFERS]
    num_aurls = aurls.count()
    t1 = now - timedelta(days=num_aurls)
    for j, aurl in enumerate(aurls):
        url = aurl.url
        if not aurl.page_title:
            urlname = viewutils.getUrlLastPart(url)
            suggestedDescr = urlname
        else:
            suggestedDescr = aurl.page_title
        activityDate = t1 + timedelta(days=j)
        expireDate = now + timedelta(days=20)
        esite = aurl.eligible_site
        with transaction.atomic():
            offer = OrbitCmeOffer.objects.create(
                user=user,
                eligible_site=esite,
                activityDate=activityDate,
                url=aurl,
                suggestedDescr=suggestedDescr,
                expireDate=expireDate,
                credits=0.5,
                sponsor=sponsor
            )
            offer.assignCmeTags()
        print('{0.pk}|{0.url}|{0.activityDate:%Y-%m-%d}'.format(offer))
        print(offer.tags.all())
