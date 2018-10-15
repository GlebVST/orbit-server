import logging
from time import sleep
from smtplib import SMTPException
from django.core import mail
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from users.models import User, Organization, OrgMember
from users.emailutils import sendJoinTeamEmail

logger = logging.getLogger('mgmt.jointeam')

class Command(BaseCommand):
    help = "Send JoinTeam email invitation for the given organization and users. First arg is Org Code and rest are user emails"

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('org_code', type=str,
                help='Organization code. User will be invited to join this org')
        parser.add_argument('user_email', type=str, nargs='+',
                help='Space separated list of user emails')

    def handle(self, *args, **options):
        try:
            org = Organization.objects.get(code=options['org_code'])
        except Organization.DoesNotExist:
            self.stdout.write('Invalid Organization Code: {0}'.format(options['org_code']))
            return
        users = []
        try:
            for v in options['user_email']:
                user = User.objects.get(email=v)
                users.append(user)
        except User.DoesNotExist:
            self.stdout.write('Invalid User Email: {0}'.format(options['user_email']))
            return
        # check user is not already an active OrgMember
        user_check = True
        for user in users:
            qset = OrgMember.objects.filter(user=user, removeDate__isnull=True)
            if qset.exists():
                m = qset[0]
                self.stdout.write('Error: User {0} is already an active member of Org {1.code}'.format(user, m.organization))
                user_check = False
        if not user_check:
            self.stdout.write('No emails sent.')
            return
        # send emails
        num_sent = 0
        try:
            connection = mail.get_connection()
            connection.open()
            msgs = [sendJoinTeamEmail(user, org, send_message=False) for user in users]
            num_sent = connection.send_messages(msgs)
        except SMTPException, e:
            error_msg = "SMTPException: {0}".format(e)
            logger.warning(error_msg)
            self.stdout.write(error_msg)
        self.stdout.write('Number of emails sent: {0}'.format(num_sent))
