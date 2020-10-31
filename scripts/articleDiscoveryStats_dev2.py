# To run:
# python manage.py shell
# from scripts import articleDiscoveryStats
# g = articleDiscoveryStats.main()
import math
import csv
import collections
from datetime import timedelta
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone
from users.models import *
from users.emailutils import makeCsvForAttachment

unsubscribed_list = []

def sendEmailBody(user, message, subject, email_addr):
    to_emails = ["logicalmath333@gmail.com", email_addr]
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

    allowed_emails = ["logicalmath333@gmail.com", "ram+discoverrad@orbitcme.com",\
                      "rsrinivasan02@hotmail.com"]

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

    one_week = today - timezone.timedelta(weeks=1)

    # dictionary where key is the user and value is number of offers in past week
    num_offers_dct = collections.defaultdict(lambda : 0)
    # dictionary where key is the user, and value is a dictionary of study topics and their counts
    offer_num_dct = collections.defaultdict(lambda : collections.defaultdict(lambda : 0))
    # dictionary where key is the user, and the value is the user's organization group
    users_orggroup_dct = collections.defaultdict(lambda : "")

    for d_user in discovery_users:
        offers = OrbitCmeOffer.objects.filter(user=d_user, activityDate__range=(one_week, today))
        num_offers_dct[d_user] = len(offers)
        for offer in offers:
            allowed_url = offer.url
            print(allowed_url, allowed_url.studyTopics.all())
            # only use one study topic so that the percentages add up to 100 percent
            if len(allowed_url.studyTopics.all()) > 0:
                num_study = len(allowed_url.studyTopics.all())
                for study_topic in allowed_url.studyTopics.all():
                    offer_num_dct[d_user][study_topic.name] += 1/num_study

        # Determine the organization group of this user
        org_member = OrgMember.objects.filter(user=d_user)
        if len(org_member) > 0:
            users_orggroup_dct[d_user] = org_member[0].group

    num_offers_data = [{'email': user.email,
                        'lastName': user.profile.lastName,
                        'firstName': user.profile.firstName,
                        'totalOffers': offers} for user, offers in num_offers_dct.items()]

    for user in num_offers_dct.keys():
        if user.email not in allowed_emails:
            continue
        message = "Orbit Discovery Weekly Summary ({0} - {1}) Version 2<br>".format(one_week.strftime("%m/%d"), today.strftime("%m/%d"))
        message += "{0} {1}<br>".format(user.profile.firstName, user.profile.lastName)
        if users_orggroup_dct[user]:
            message += "{0}<br>".format(users_orggroup_dct[user])
        message += "Total number of articles read this week: {0}<br>".format(num_offers_dct[user])
        message += "Distribution of topics this week: <br>"
        message += "<table><tr><th>Study Topic</th><th>Percentage of Offers</th></tr>"
        other = num_offers_dct[user]
        study_topic_lst = []
        for study_topic in StudyTopic.objects.all():
            study_topic_lst.append((study_topic.name.lower(), study_topic))
        # sort alphabetically the study topic list
        study_topic_lst.sort()
        tagged_num_study_topics = 0

        # get the total count of tagged offers
        for _, study_topic in study_topic_lst:
            count = offer_num_dct[user][study_topic.name]
            tagged_num_study_topics += count


        # Adding the study topics table
        for topic, study_topic in study_topic_lst:
            if tagged_num_study_topics > 0:
                study_topic_percent = round(offer_num_dct[user][study_topic.name] * 100/tagged_num_study_topics)
            else:
                study_topic_percent = 0
            message += "<tr><td>{0}</td><td>{1}%</td></tr>".format(topic, study_topic_percent)

        message += "</table>"
        message += "-Your Orbit Team <br>"
        message += "To unsubscribe, please email support@orbitcme.com"
        subject='Discovery Weekly Summary ({0} - {1}) Version 2'.format(one_week.strftime("%m/%d"), today.strftime("%m/%d"))

        sendEmailBody(user, message, subject, user.email)


    return offer_num_dct

