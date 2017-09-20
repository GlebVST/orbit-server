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
    NUM_OFFERS = 10
    sponsor = Sponsor.objects.get(pk=1)
    # the EligibleSites appropriate for this user
    esiteids = EligibleSite.objects.getSiteIdsForProfile(user.profile)
    # exclude urls for which user already has un-redeemed un-expired offers waiting to be redeemed
    now = timezone.now()
    exclude_urls = BrowserCmeOffer.objects.filter(
        user=user,
        redeemed=False,
        eligible_site__in=esiteids,
        expireDate__gte=now
    ).values_list('url', flat=True).distinct()
    print('Num exclude_urls: {0}'.format(len(exclude_urls)))
    aurls = AllowedUrl.objects.filter(eligible_site__in=esiteids).exclude(url__in=exclude_urls).order_by('?')[:NUM_OFFERS]
    num_aurls = aurls.count()
    t1 = now - timedelta(days=num_aurls)
    for j, aurl in enumerate(aurls):
        url = aurl.url
        print(url)
        if not aurl.page_title:
            urlname = viewutils.getUrlLastPart(url)
            pageTitle = urlname
            suggestedDescr = urlname
        else:
            pageTitle = aurl.page_title
            suggestedDescr = aurl.page_title
        activityDate = t1 + timedelta(days=j)
        expireDate = now + timedelta(days=20)
        esite = aurl.eligible_site
        specnames = [p.name for p in esite.specialties.all()]
        spectags = CmeTag.objects.filter(name__in=specnames)
        with transaction.atomic():
            offer = BrowserCmeOffer.objects.create(
                user=user,
                eligible_site=esite,
                activityDate=activityDate,
                url=url,
                pageTitle=pageTitle,
                suggestedDescr=suggestedDescr,
                expireDate=expireDate,
                credits=0.5,
                sponsor=sponsor
            )
            for t in spectags:
                OfferCmeTag.objects.create(offer=offer, tag=t)
        print user.username, urlname, offer.pk, activityDate.strftime('%Y-%m-%d')

def redeemOffers(user):
    """Redeem unexpired offers and create BrowserCme entries in feed"""
    etype = EntryType.objects.get(name=ENTRYTYPE_BRCME)
    userTags = user.profile.cmeTags.all().order_by('name')
    num_tags = userTags.count()
    now = timezone.now()
    offers = BrowserCmeOffer.objects.filter(
        user=user,
        redeemed=False,
        expireDate__gt=now
    ).order_by('activityDate')
    for offer in offers:
        rtag = userTags[randint(0, num_tags-1)]
        print offer.pk, offer.url, offer.activityDate
        with transaction.atomic():
            entry = Entry.objects.create(
                entryType=etype,
                user=user,
                sponsor=offer.sponsor,
                description='some description text',
                activityDate=offer.activityDate
            )
            entry.tags.set([rtag.pk,])
            brcme = BrowserCme.objects.create(
                entry=entry,
                offer=offer,
                url=offer.url,
                pageTitle=offer.pageTitle,
                credits=offer.credits,
                purpose=randint(0,1),
                planEffect=randint(0,1)
            )
            offer.redeemed = True
            offer.save()
            print('Entry {0.pk} tag:{1.name}'.format(entry, rtag))
