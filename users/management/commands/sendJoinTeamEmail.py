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
    help = "Send JoinTeam email invitation to existing user[s]. First arg is Org joinCode and rest are user emails"

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('orgcode', type=str,
                help='Organization joincode (no whitespace). User will be invited to join this org')
        parser.add_argument('user_email', type=str, nargs='+',
                help='Space separated list of user emails')

    def handle(self, *args, **options):
        try:
            org = Organization.objects.get(joinCode=options['orgcode'])
        except Organization.DoesNotExist:
            self.stdout.write('Invalid Organization joinCode: {0}'.format(options['orgcode']))
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
        toCreate = []
        for user in users:
            qset = OrgMember.objects.filter(user=user, organization=org)
            if qset.exists():
                m = qset[0]
                if m.pending:
                    logger.info('User is already pending OrgMember {0}'.format(m))
                elif m.removeDate is not None:
                    logger.info('User {0} is removed OrgMember {1.pk}. Set pending to True'.format(user, m))
                    m.pending = True
                    m.save(update_fields=('pending',))
                else:
                    self.stdout.write('Error: User {0} is already an active member of Org {1.code}'.format(user, m.organization))
                    user_check = False
            else:
                toCreate.append(user)
        if not user_check:
            self.stdout.write('No emails sent.')
            return
        # Create pending OrgMembers
        for user in toCreate:
            m = OrgMember.objects.createMember(org, user.profile, pending=True)
            logger.info('Created pending OrgMember {0}'.format(m))
        # send emails (to all users in case they did not receive it the first time)
        num_sent = 0
        try:
            connection = mail.get_connection()
            connection.open()
            msgs = [sendJoinTeamEmail(user, org, send_message=False) for user in users]
            num_sent = connection.send_messages(msgs)
        except SMTPException as e:
            error_msg = "SMTPException: {0}".format(e)
            logger.warning(error_msg)
            self.stdout.write(error_msg)
        self.stdout.write('Number of emails sent: {0}'.format(num_sent))
