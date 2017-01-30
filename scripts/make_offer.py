import os
from users.models import *
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from common import viewutils
from random import randint

urls = (
    'https://radiopaedia.org/cases/traumatic-direct-caroticocavernous-fistula',
    'https://radiopaedia.org/articles/meningioma',
    'https://radiopaedia.org/articles/lung-cancer-3',
    'https://radiopaedia.org/articles/15t-vs-3t',
    'https://radiopaedia.org/articles/mri-introduction',
    'https://radiopaedia.org/articles/mr-physics',
    'https://radiopaedia.org/articles/mri-safety',
    'https://radiopaedia.org/articles/endocrine-tumours-of-the-pancreas',
    'https://radiopaedia.org/articles/pancreatic-trauma-1',
    'https://radiopaedia.org/articles/pancreatic-lipomatosis',
    'https://radiopaedia.org/articles/oesophageal-stricture',
    'http://www.mdcalc.com/cha2ds2-vasc-score-atrial-fibrillation-stroke-risk/',
    'http://www.mdcalc.com/creatinine-clearance-cockcroft-gault-equation/',
    'http://www.mdcalc.com/wells-criteria-pulmonary-embolism/',
    'http://www.mdcalc.com/sirs-sepsis-septic-shock-criteria/'
)

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
    now = timezone.now()
    t1 = now - timedelta(days=20)
    for url in urls:
        urlname = viewutils.getUrlLastPart(url)
        activityDate = t1 + timedelta(days=1)
        expireDate = activityDate + timedelta(days=60)
        offer = BrowserCmeOffer.objects.create(
            user=user,
            activityDate=activityDate,
            url=url,
            pageTitle=urlname,
            expireDate=expireDate,
            points=1,
            credits=0.5
        )
        print user.username, urlname, offer.pk

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
            print('Entry {0} credits {1} tag:{2}'.format(entry.pk, brcme.credits, rtag.name))
