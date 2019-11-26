"""Collect and format OrbitCME data to be submitted to ABA (American Board of Anesthesiology)"""
import logging
from datetime import datetime
from operator import itemgetter
from time import sleep
from smtplib import SMTPException
from django.core.mail import EmailMessage
from django.core import mail
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.template.loader import get_template
from django.utils import timezone
from users.models import User, Profile, Entry, UserSubscription
from users.emailutils import setCommonContext, makeCsvForAttachment

logger = logging.getLogger('mgmt.abarp')

EVENT_ID = 'EVENT ID (Max 10 Characters)'
EVENT_DESCR = 'EVENT DESCRIPTION'

E_PROVIDER_ID = 'ABA Provider_ID'
E_CATG = 'Category1 - Y or N'
P_ABA_ID = 'ABA (ACCME) ID'
P_PROVIDER_ID = 'Provider ID'
P_DATE_COMPLETED = 'Date Completed'
P_CREDITS = 'Credits Awarded'

EVENT_FIELDS = (
    E_PROVIDER_ID,
    EVENT_ID,
    EVENT_DESCR,
    E_CATG
)

PARTICIPANT_FIELDS = (
    P_ABA_ID,
    P_PROVIDER_ID,
    EVENT_ID,
    P_DATE_COMPLETED,
    P_CREDITS
)

class Command(BaseCommand):
    help = "If there is data to send, create Event/Participant CSV files, and email them to ABA (American Board of Anesthesiology)."

    def getEligibleProfiles(self):
        profiles = []
        qs = Profile.objects.getProfilesForABA() # Profile queryset
        for p in qs:
            if not p.ABANumber:
                continue
            us = UserSubscription.objects.getLatestSubscription(p.user)
            if us.display_status in (UserSubscription.UI_ACTIVE, UserSubscription.UI_ACTIVE_CANCELED, UserSubscription.UI_ACTIVE_DOWNGRADE):
                profiles.append(p)
        return profiles

    def sendEmail(self, reportDate, eventData, participantData):
        reportDateFname = reportDate.strftime("%m-%d-%y")
        # make csv attachments
        cfEvent = makeCsvForAttachment(EVENT_FIELDS, eventData)
        eventFileName = 'orbit_{0}_event_file.csv'.format(reportDateFname)
        cfParticipant = makeCsvForAttachment(PARTICIPANT_FIELDS, participantData)
        participantFileName = 'orbit_{0}_participation_file.csv'.format(reportDateFname)

        # create EmailMessage
        from_email = settings.SUPPORT_EMAIL
        if settings.ENV_TYPE == settings.ENV_PROD:
            #to_emails = [settings.ABA_CME_EMAIL,]
            to_emails = ['ram+ABAsync@orbitcme.com']
            #cc_emails = ['ram+ABAsync@orbitcme.com']
            bcc_emails = ['faria+ABAsync@orbitcme.com',]
        else:
            to_emails = ['faria@orbitcme.com',]
            cc_emails = []
            bcc_emails = []
        reportDateStr = reportDate.strftime("%m/%d/%y")
        subject = "[Orbit-ABA LLS Data] {0}".format(reportDateStr)
        ctx = {
            'reportDate': reportDate,
            'ABA_ACCME_ID': settings.ABA_ACCME_ID,
            'companyName': settings.COMPANY_NAME,
        }
        setCommonContext(ctx)
        message = get_template('email/aba_cme_report.html').render(ctx)
        msg = EmailMessage(
                subject,
                message,
                to=to_emails,
                cc=cc_emails,
                bcc=bcc_emails,
                from_email=from_email)
        msg.content_subtype = 'html'
        msg.attach(eventFileName, cfEvent, 'application/octet-stream')
        msg.attach(participantFileName, cfParticipant, 'application/octet-stream')
        try:
            msg.send()
        except SMTPException as e:
            logger.exception('sendABAReport email failed')
            return False
        else:
            logger.info('sendABAReport email done')
            return True

    def handle(self, *args, **options):
        reportDate = timezone.now()
        reportDateStr = reportDate.strftime("%m/%d/%y")
        # get eligible users whose data will be submitted
        profiles = self.getEligibleProfiles()
        eventData = [] # data for Event file
        participantData = [] # data for Participant file
        entry_qsets = [] # list of Entry querysets to update after email is sent
        for profile in profiles:
            userABANumber = profile.formatABANumber()
            print(profile.user)
            userData = Entry.objects.prepareDataForABAReport(profile.user)
            userData.sort(key=itemgetter('eventId'))
            for d in userData:
                print(" -- {eventId} {eventDescription} {brcme_sum}".format(**d))
                eventData.append({
                    E_PROVIDER_ID: userABANumber,
                    EVENT_ID: d['eventId'],
                    EVENT_DESCR: d['eventDescription'],
                    E_CATG: d['isCategory1']
                })
                participantData.append({
                    P_ABA_ID: settings.ABA_ACCME_ID,
                    P_PROVIDER_ID: userABANumber,
                    EVENT_ID: d['eventId'],
                    P_DATE_COMPLETED: reportDateStr,
                    P_CREDITS: str(d['brcme_sum'])
                })
                entry_qsets.append(d['entries'])
        if not eventData:
            logger.info('No eventData for this run. Exiting.')
        else:
            success = self.sendEmail(reportDate, eventData, participantData)
            if success:
                # bulk-update of submitABADate field for the reported entries
                for qs in entry_qsets:
                    qs.update(submitABADate=reportDate)
                logger.info('sendABAReport updated submitABAData on entries')
