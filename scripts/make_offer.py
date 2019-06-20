import os
import pytz
from users.models import *
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from common import viewutils
from random import randint

NUM_OFFERS = 10
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

def makeOffers(user, num_offers=None):
    sponsor = Sponsor.objects.get(pk=1)
    # the EligibleSites appropriate for this user
    esiteids = EligibleSite.objects.getSiteIdsForProfile(user.profile)
    # exclude urls for which user already has un-expired offers waiting to be redeemed
    now = timezone.now()
    exclude_urls = OrbitCmeOffer.objects.filter(
        user=user,
        expireDate__gte=now)
    # get aurls
    aurls = AllowedUrl.objects \
        .filter(
            valid=True,
            eligible_site__in=esiteids,
            content_type__istartswith='text/html'
        ) \
        .exclude(pk__in=Subquery(exclude_urls.values('url'))) \
        .order_by('?')[:num_offers]
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
        expireDate = now + timedelta(days=365)
        esite = aurl.eligible_site
        with transaction.atomic():
            offer = OrbitCmeOffer.objects.create(
                user=user,
                eligible_site=esite,
                activityDate=activityDate,
                url=aurl,
                suggestedDescr=suggestedDescr,
                expireDate=expireDate,
                credits=ARTICLE_CREDIT,
                sponsor=sponsor
            )
            offer.assignCmeTags()
        print('{0.pk}|{0.url}|{0.activityDate:%Y-%m-%d}'.format(offer))
        #print(offer.tags.all())

def makeOffersForRecs(user, tag):
    """Generate offer for recaurl and set recaurl.offer"""
    sponsor = Sponsor.objects.get(pk=1)
    recaurls = user.recaurls.select_related('url').filter(cmeTag=tag, offer__isnull=True).order_by('id')
    now = timezone.now()
    t1 = now - timedelta(days=1)
    for j, recaurl in enumerate(recaurls[0:5]):
        activityDate = t1 + timedelta(seconds=j)
        expireDate = now + timedelta(days=365)
        aurl = recaurl.url
        esite = aurl.eligible_site
        url = aurl.url
        if aurl.page_title:
            suggestedDescr = aurl.page_title
        else:
            urlname = viewutils.getUrlLastPart(url)
            suggestedDescr = urlname
        with transaction.atomic():
            offer = OrbitCmeOffer.objects.create(
                user=user,
                eligible_site=esite,
                activityDate=activityDate,
                url=aurl,
                suggestedDescr=suggestedDescr,
                expireDate=expireDate,
                credits=ARTICLE_CREDIT,
                sponsor=sponsor
            )
            offer.assignCmeTags()
            recaurl.offer = offer
            recaurl.save(update_fields=('offer',))
            # check if can assign this offer to other recs for this same aurl
            qs = user.recaurls.filter(url=aurl, offer__isnull=True)
            for ra in qs:
                ra.offer = offer
                recaurl.save(update_fields=('offer',))
        print('{0.pk}|{0.url}|{0.activityDate:%Y-%m-%d} assigned to recaurl {1.pk}|{1.cmeTag}'.format(offer, recaurl))

