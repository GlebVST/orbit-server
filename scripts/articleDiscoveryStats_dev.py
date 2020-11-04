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
    reply_emails = ['support@orbitcme.com']

    msg = EmailMessage(
            subject,
            message,
            to=to_emails,
            cc=[],
            bcc=[],
            reply_to=reply_emails,
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

    # used to generate the table with the email/url/study topics (in form of csv)
    articleStudyData = []

    topic_counter = collections.Counter()
    topic_org_counter = collections.defaultdict(lambda : collections.Counter())

    for d_user in discovery_users:
        offers = OrbitCmeOffer.objects.filter(user=d_user, activityDate__range=(one_week, today))
        num_offers_dct[d_user] = len(offers)

        # Determine the organization group of this user
        org_member = OrgMember.objects.filter(user=d_user)
        if len(org_member) > 0:
            users_orggroup_dct[d_user] = org_member[0].group

        # go through all of the offers and the study topics associated with each url/offer
        for offer in offers:
            allowed_url = offer.url
            # only use weighted study topic so that the percentages add up to 100 percent
            if len(allowed_url.studyTopics.all()) > 0:
                num_study_topics = len(allowed_url.studyTopics.all())
                study_topics_names = [s.name.lower() for s in allowed_url.studyTopics.all()]
                # this is used to generate the table with email/url/study topics
                d = {'email': d_user.email, 'url': allowed_url,
                    'study topics': ", ".join(study_topics_names)}
                articleStudyData.append(d)
                for study_topic in allowed_url.studyTopics.all():
                    offer_num_dct[d_user][study_topic.name] += 1/num_study_topics

                    # counters of study topics overall and by org
                    topic_name = study_topic.name.lower()
                    topic_counter[topic_name] += 1

                    if d_user in users_orggroup_dct:
                        topic_org_counter[users_orggroup_dct[d_user]][topic_name] += 1

    num_offers_data = [{'email': user.email,
                        'lastName': user.profile.lastName,
                        'firstName': user.profile.firstName,
                        'totalOffers': offers} for user, offers in num_offers_dct.items()]

    topic_abbreviations = set(["ai", "h&n", "gi", "gu", "ir", "msk", "nis"])

    most_popular_topic = [key for key in topic_counter if topic_counter[key] == max(topic_counter.values())]
    if most_popular_topic:
        if most_popular_topic[0] in topic_abbreviations:
            most_popular_topic = most_popular_topic[0].upper()
        else:
            most_popular_topic = most_popular_topic[0]

    org_popular_topic = {}
    print(topic_org_counter)
    for org, topics in topic_org_counter.items():
        org_popular_topic[org] = [key for key in topics if topics[key] == max(topics.values())]
        if org_popular_topic[org]:
            if org_popular_topic[org][0] in topic_abbreviations:
                org_popular_topic[org] = org_popular_topic[org][0].upper()
            else:
                org_popular_topic[org] = org_popular_topic[org][0]

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
        message += "Happy Friday. "
        print(users_orggroup_dct[user])
        print(org_popular_topic)
        if most_popular_topic:
            message += "This week in Orbit Discovery, "

        if users_orggroup_dct[user] and org_popular_topic[users_orggroup_dct[user]]:
            org = users_orggroup_dct[user]
            message += "the most popular topic at {0} was {1}, and ".format(org, org_popular_topic[org])

        if most_popular_topic:
            message += "the most popular topic across the country was {0}. ".format(most_popular_topic)
        message += "<br>Your summary for the week is below. To capture all of your progress "
        message += "on service or while studying, stay logged into Orbit - on your Chrome browser, iPhone, or iPad."
        message += "<ul>"
        message += '<li>Orbit for Chrome [<a href="https://chrome.google.com/webstore/detail/orbit-for-chrome/ffbnancjlgeeeipcmpiikloifeimgglf">here</a>]</li>'
        message += '<li>uBlock Origin for Chrome [<a href="https://chrome.google.com/webstore/detail/ublock-origin/cjpalhdlnbpafiamejdnhcphjbkeiagm?hl=en">here</a>]</li>'
        message += '<li>Orbit for iPhone and iPad [<a href="https://apps.apple.com/us/app/orbit-cme-search-discover/id1524243733">here</a>]</li>'
        message += "</ul>"
        message += "Reporting period: {0} - {1}".format(one_week.strftime("%m/%d"), today.strftime("%m/%d"))
        message += "<br>Unique article visits: {0}<br><br>".format(num_offers_dct[user])

        message += "<table><tr><th>Topic</th><th>Percent Effort</th></tr>"
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
            if topic in topic_abbreviations:
                topic = topic.upper()
            #if study_topic_percent != 0:
            #    message += '<tr bgcolor="lightgrey"><td>{0}</td><td>{1}%</td></tr>'.format(topic, study_topic_percent)
            #else:
            message += '<tr><td>{0}</td><td>{1}%</td></tr>'.format(topic, study_topic_percent)

        message += "</table>"
        message += """\
            </body>
        </html>
        """
        message += "<br>Best wishes, <br>"
        message += "Orbit Support <br>"
        message += "<br>Questions? Please email support@orbitcme.com"

        subject='({0} - {1}) Your week in Orbit Discovery'.format(one_week.strftime("%m/%d"), today.strftime("%m/%d"))
        #subject='Discovery Weekly Summary ({0} - {1}) Version {2}'.format(one_week.strftime("%m/%d"), today.strftime("%m/%d"), version)
        sendEmailBody(user, message, subject, user.email)

    attachments = [
        dict(fileName='article_study_topics.csv', contentFile=makeCsvAttachment('articleStudy', articleStudyData))
    ]

    sendEmailWithAttachment(attachments)

    return offer_num_dct

