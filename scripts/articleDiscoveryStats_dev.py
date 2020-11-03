# To run:
# python manage.py shell
# from scripts import articleDiscoveryStats
# g = articleDiscoveryStats.main()
# g = articleDiscoveryStats.main(1) runs version 1
# g = articleDiscoveryStats.main(2) runs version 2
# g = articleDiscoveryStats.main(3) runs version 3, 
# which has the "other" study topic
import math
import csv
import collections
from datetime import timedelta
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone
from users.models import *
from users.emailutils import makeCsvForAttachment

fieldNamesMap = {
    'articleStudy': ('email', 'url', 'study topics')
}

def sendEmailBody(user, message, subject, email_addr):
    ''' This is used to send the weekly stats email'''
    #to_emails = ['logicalmath333@gmail.com', email_addr]
    to_emails = ['logicalmath333@gmail.com', 'ram@orbitcme.com']
    #to_emails = ['logicalmath333@gmail.com']

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

def makeCsvAttachment(tabName, data):
    fieldNames = fieldNamesMap[tabName]
    cf = makeCsvForAttachment(fieldNames, data)
    return cf

def sendEmailWithAttachment(attachments):
    ''' This is used to generate the table of urls and 
        associated study topics
    '''
    to_emails = ['logicalmath333@gmail.com']
    subject = "Url and Study topics stats"
    message = "See attached csv"
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

def main(version):

    #allowed_emails = ["logicalmath333@gmail.com", "ram+discoverrad@orbitcme.com",\
    #                  "rsrinivasan02@hotmail.com", ]

    allowed_emails = ["allenqye@gmail.com"]

    discovery_plan_names = ["Discover Monthly", "Discover Radiology Explorer",\
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

    articleStudyData = []
    for d_user in discovery_users:
        offers = OrbitCmeOffer.objects.filter(user=d_user, activityDate__range=(one_week, today))
        num_offers_dct[d_user] = len(offers)
        for offer in offers:
            allowed_url = offer.url
            print(allowed_url, allowed_url.studyTopics.all())
            # only use weighted study topic so that the percentages add up to 100 percent
            if len(allowed_url.studyTopics.all()) > 0:
                num_study_topics = len(allowed_url.studyTopics.all())
                study_topics_names = [s.name.lower() for s in allowed_url.studyTopics.all()]
                d = {'email': d_user.email, 'url': allowed_url,
                    'study topics': ", ".join(study_topics_names)}
                articleStudyData.append(d)
                for study_topic in allowed_url.studyTopics.all():
                    offer_num_dct[d_user][study_topic.name] += 1/num_study_topics
                    print(d_user.email, study_topic.name.lower())
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

        message = """\
            <html>
                <head>
                    <style>
                    table {
                        font-family: arial, sans-serif;
                        border-collapse: collapse;
                        width: 100%;
                        }   
                        td, th {
                            border: 1px solid #dddddd;
                            text-align: left;
                            padding: 8px;
                        }   
                        tr:nth-child(even) {
                            background-color: #dddddd;
                        }   
                    </style>            
                </head>
            <body>
        """
        message += "Dear {0}, <br>".format(user.profile.firstName)
        if users_orggroup_dct[user]:
            message += "Hope all is well at {0}! ".format(users_orggroup_dct[user])
        message += "Here's your weekly progress report ({0} - {1}) of topics you covered while logged into Orbit on your Chrome browser, iPhone or iPad:<br>"\
                .format(one_week.strftime("%m/%d"), today.strftime("%m/%d"))
        message += "<br>Unique article visits: {0}<br><br>".format(num_offers_dct[user])

        message += "<table><tr><th>Study Topic</th><th>Percent Effort</th></tr>"
        other = num_offers_dct[user]
        study_topic_lst = []
        study_topic_offers = []
        for study_topic in StudyTopic.objects.all():
            study_topic_lst.append((study_topic.name.lower(), study_topic))

        for study_topic in offer_num_dct[user]:
            count = offer_num_dct[user][study_topic]
            other = other - count

        other = max(other, 0)
        if other > 0 and version == 3:
            study_topic_lst.append(("other", None))

        if version in [1,2]:
            tagged_num_study_topics = 0

            # get the total count of tagged offers
            for _, study_topic in study_topic_lst:
                count = offer_num_dct[user][study_topic.name]
                tagged_num_study_topics += count

        # sort alphabetically the study topic list
        study_topic_lst.sort()

        if version == 2:
            # sort by percentage, and then alphabetically
            study_topic_lst.sort(key=lambda x: (-offer_num_dct[user][x[1].name], x[0]))

        #study_topic_offers.sort(reverse=True)
        # Adding the study topics table
        for topic, study_topic in study_topic_lst:
            if version in [1, 2]:
                if tagged_num_study_topics > 0:
                    study_topic_percent = round(offer_num_dct[user][study_topic.name] * 100/tagged_num_study_topics)
                else:
                    study_topic_percent = 0
            elif version == 3:
                num_offers = num_offers_dct[user]
                name = ""
                if topic == "other" and num_offers > 0:
                    study_topic_percent = round(other * 100/num_offers)
                elif num_offers > 0:
                    study_topic_percent = round(offer_num_dct[user][study_topic.name] * 100/num_offers)
                else:
                    study_topic_percent = 0
            if study_topic_percent != 0:
                message += '<tr bgcolor="lightgreen"><td>{0}</td><td>{1}%</td></tr>'.format(topic, study_topic_percent)
            else:
                message += '<tr><td>{0}</td><td>{1}%</td></tr>'.format(topic, study_topic_percent)

        message += "</table>"
        message += """\
            </body>
        </html>
        """
        message += "-Your Orbit Team <br>"
        message += "To unsubscribe, please email support@orbitcme.com"

        subject='Discovery Weekly Summary ({0} - {1}) Version {2}'.format(one_week.strftime("%m/%d"), today.strftime("%m/%d"), version)
        sendEmailBody(user, message, subject, user.email)

    attachments = [
        dict(fileName='article_study_topics.csv', contentFile=makeCsvAttachment('articleStudy', articleStudyData))
    ]

    sendEmailWithAttachment(attachments)

    return offer_num_dct

