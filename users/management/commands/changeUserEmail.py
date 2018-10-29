import logging
import os
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from users.models import User, Profile
from users.auth0_tools import Auth0Api

logger = logging.getLogger('mgmt.updemail')

class Command(BaseCommand):
    help = "Update user email from old to new. This checks that new_email does not already exist in the system."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('old_email')
        parser.add_argument('new_email')

    def handle(self, *args, **options):
        old_email = options['old_email']
        new_email = options['new_email']
        if not User.objects.filter(email=old_email).exists():
            raise ValueError('Invalid old_email. User does not exist.')
            return
        user = User.objects.get(email=old_email)
        profile = user.profile
        if User.objects.filter(email=new_email).exists():
            raise ValueError('Invalid new_email. A user with this email already exists in the system.')
            return
        # connect to auth0
        api = Auth0Api()
        verify_email = True if settings.ENV_TYPE == settings.ENV_PROD else False
        logger.info('Updating auth0 account for: {0.socialId}'.format(profile))
        res = api.updateUser(profile.socialId, new_email, verify_email)
        print('auth0 email: {email} updated_at: {updated_at}'.format(**res))
        profile.verified = False
        profile.save()
        user.username = new_email
        user.email = new_email
        user.save()
        logger.info('Updated User from {0} to {1}'.format(old_email, new_email))
