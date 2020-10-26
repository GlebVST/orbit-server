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
    'total_offers': ('email', 'lastName', 'firstName', 'totalOffers'),
    'providers': ('status','email','lastName','firstName','group','birthDate','age','creditsRedeemed'),
    'groups': ('group','totalCredits','avgCreditsPerProvider','numActiveProviders','totalProviders'),
    'age': ('age','totalCredits','avgCreditsPerProvider','numActiveProviders','totalProviders'),
    'tags': ('tag','totalCredits'),
    'oagg': ('year','month','activeUsers','invitedUsers','totalUsers','addedUsers','expiredLicenses','expiredCMEGap')
}

unsubscribed_list = []

def makeCsvAttachment(tabName, data):
    fieldNames = fieldNamesMap[tabName]
    cf = makeCsvForAttachment(fieldNames, data)
    return cf

def sendEmail(attachments):
    to_emails = ['logicalmath333@gmail.com',]
    subject='Orbit Discovery Article stats'
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

def sendEmailBody(user, message):
    to_emails = ['logicalmath333@gmail.com',]
    subject='Orbit Discovery Article stats'
    msg = EmailMessage(
            subject,
            message,
            to=to_emails,
            cc=[],
            bcc=[],
            from_email=settings.EMAIL_FROM)
    msg.content_subtype = 'html'
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

    discovery_plan_names = ["Discover Monthly", "Discover Radiology Explorer", \
                            "Discover Annual", "Discover Radiology", "Discover Radiology Pilot"]

    discovery_plans = []
    for d_plan_name in discovery_plan_names:
        discovery_plan = SubscriptionPlan.objects.filter(name=d_plan_name)
        discovery_plans.extend([d for d in discovery_plan])


    discovery_users = []
    for d_plan in discovery_plans:    
        users_sub = UserSubscription.objects.filter(plan=d_plan)
        discovery_users.extend([u.user for u in users_sub])

    now = timezone.now()
    today = now.date()

    one_week = today - timezone.timedelta(weeks=10)

    num_offers_dct = collections.defaultdict(lambda : 0)
    offer_percent_dct = collections.defaultdict(lambda : collections.defaultdict(lambda : 0))

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

    num_offers_data = [{'email': user.email, 
                        'lastName': user.profile.lastName, 
                        'firstName': user.profile.firstName, 
                        'totalOffers': offers} for user, offers in num_offers_dct.items()]

    for user in num_offers_dct.keys():
        message = "Hi {0} {1}\n".format(user.profile.firstName, user.profile.lastName)
        message += "Great job with your studying! Here's a breakdown of what's happened in the past week: \n"
        message += "Total number of articles read: {0}\n".format(num_offers_dct[user])
        message += "Study topics: \n"
        for study_topic in offer_percent_dct[user]:
            message += "{0}: {1}".format(study_topic, offer_percent_dct[user][study_topic])
            
        sendEmailBody(user, message)
    #attachments = [
    #    dict(fileName='discovery_orbitcme.csv', contentFile=makeCsvAttachment('total_offers', num_offers_data))
    #]

    #sendEmail(attachments)
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
