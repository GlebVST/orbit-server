import logging
import os
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from auth0.v3.authentication import GetToken
from auth0.v3.management import Auth0
from auth0.v3.exceptions import Auth0Error
from users.models import User, Profile

logger = logging.getLogger('mgmt.updemail')

class Command(BaseCommand):
    help = "Update user email from old to new. This checks that new_email does not already exist in the system."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('old_email')
        parser.add_argument('new_email')

    def handle(self, *args, **options):
        # from .env file
        client_id = os.environ['ORBIT_AUTH0_MGMT_CLIENTID']
        client_secret = os.environ['ORBIT_AUTH0_MGMT_CLIENT_SECRET']
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
        domain = settings.AUTH0_DOMAIN
        mgmt_url = 'https://{0}/api/v2/'.format(domain)
        get_token = GetToken(domain)
        # returns dict with keys: access_token, scope, expires_in, token_type
        token = get_token.client_credentials(client_id, client_secret, mgmt_url)
        acc_token = token['access_token']
        conn = Auth0(domain, acc_token)
        logger.info('Update auth0 account: {0.socialId}'.format(profile))
        body={'email': new_email}
        if settings.ENV_TYPE == settings.ENV_PROD:
            body['verify_email'] = True # trigger a verify email msg to the user
        else:
            body['email_verified'] = False # no trigger in test
        try:
            res = conn.users.update(id=profile.socialId, body=body)
        except Auth0Error, e:
            logger.exception('Auth0Error for update email')
        else:
            print('auth0 email: {email} name: {name} updated_at: {updated_at}'.format(**res))
            profile.verified = False
            profile.save()
            user.username = new_email
            user.email = new_email
            user.save()
            logger.info('Updated User from {0} to {1}'.format(old_email, new_email))
            print('Updated User from {0} to {1}'.format(old_email, new_email))
