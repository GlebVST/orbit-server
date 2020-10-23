"""Report used for RP pricing"""
import csv 
import collections
from datetime import timedelta
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone
from users.models import *
from users.emailutils import makeCsvForAttachment

fieldNamesMap = { 
    'providers': ('status','email','lastName','firstName','group','birthDate','age','creditsRedeemed'),
    'groups': ('group','totalCredits','avgCreditsPerProvider','numActiveProviders','totalProviders'),
    'age': ('age','totalCredits','avgCreditsPerProvider','numActiveProviders','totalProviders'),
    'tags': ('tag','totalCredits'),
    'oagg': ('year','month','activeUsers','invitedUsers','totalUsers','addedUsers','expiredLicenses','expiredCMEGap')
}

def makeCsvAttachment(tabName, data):
    fieldNames = fieldNamesMap[tabName]
    cf = makeCsvForAttachment(fieldNames, data)
    return cf

def sendEmail(attachments):
    to_emails = ['logicalmath333@gmail.com',]
    subject='RP Stats Oct 2019'
    message = 'See attached files'
    msg = EmailMessage(
            subject,
            message,
            to=to_emails,
            cc=[],
            bcc=[],
            from_email=settings.EMAIL_FROM)
    msg.content_subtype = 'html'
    for d in attachments:
        msg.attach(d['fileName'], d['contentFile'], 'application/octet-stream')
    msg.send()
    print('Email sent')

def main():

    #providers = org.orgmembers \
    #    .filter(is_admin=False) \
    #    .select_related('group', 'user__profile') \
    #    .order_by('user__profile__lastName','user__profile__firstName','id')
    #providerData = makeProviderData(providers)
    #tagData = makeTagData(providerData)
    #groupData = makeGroupData(providerData)
    #ageData = makeAgeData(providerData)
    #oaggData = makeOrgAggData(org, startMY=(2, 2019), endMY=(10,2019))

    discovery_plans = []
    discovery_monthly = SubscriptionPlan.objects.filter(name="Discover Monthly")
    discovery_plans.extend([d for d in discovery_monthly])

    discovery_users = []
    for d_plan in discovery_plans:    
        users_sub = UserSubscription.objects.filter(plan=d_plan)
        discovery_users.extend([u.user for u in users_sub])

    now = timezone.now()
    today = now.date()

    one_week = today - timezone.timedelta(weeks=10)

    num_offers_dct = collections.defaultdict(lambda : 0)
    offer_percent_dct = collections.defaultdict(lambda : {})

    for d_user in discovery_users:
        offers = OrbitCmeOffer.objects.filter(user=d_user, activityDate__range=(one_week, today))
        num_offers_dct[d_user] = len(offers)
        for offer in offers:
            allowed_url = offer.url
            print(allowed_url.studyTopics.all())
            for study_topic in allowed_url.studyTopics.all(): 
                offer_percent_dct[d_user][study_topic.name] += 1/len(offers) 

    print(num_offers_dct)
    print(offer_percent_dct)

    return offer_percent_dct

    #OrbitCmeOffer.objects.get(user="logicalmath33
    '''
    attachments = [
        #dict(fileName='providers.csv', contentFile=makeCsvAttachment('providers', providerData)),
        #dict(fileName='groups.csv', contentFile=makeCsvAttachment('groups', groupData)),
        #dict(fileName='age.csv', contentFile=makeCsvAttachment('age', ageData))
        #dict(fileName='tags.csv', contentFile=makeCsvAttachment('tags', tagData))
        dict(fileName='oagg.csv', contentFile=makeCsvAttachment('oagg', oaggData))
    ]
    sendEmail(attachments)
    return oaggData
    '''
