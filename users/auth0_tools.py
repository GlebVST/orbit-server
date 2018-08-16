import logging
from datetime import datetime, timedelta
import time
from django.utils import timezone
from auth0.v3.authentication import GetToken
from auth0.v3.management import Auth0
from auth0.v3.management.rest import Auth0Error
from django.conf import settings

logger = logging.getLogger('gen.auth0')

DEFAULT_CONN_NAME = 'Username-Password-Authentication'
API_URL = 'https://{0}/api/v2/'.format(settings.AUTH0_DOMAIN)

class Auth0Api(object):

    @classmethod
    def getConnection(cls, request):
        """Create Auth0Api instance with acc_token retrieved from session.
        Args:
            request: request object with session
        Update session if existing acc_token is expired or does not exist
        Returns: Auth0Api instance
        """
        now = timezone.now()
        now_ts = time.mktime(now.timetuple()) # use now.timestamp in py3
        do_save = False
        acc_token = request.session.get('auth0_token', None)
        if not acc_token:
            do_save = True
        else:
            acc_token_expire = request.session.get('auth0_token_expire', None) # <float> seconds
            if not acc_token_expire:
                acc_token = None
                do_save = True
            elif acc_token_expire < now_ts:
                acc_token = None
                do_save = True
        apiConn = cls(acc_token)
        if do_save:
            request.session['auth0_token'] = apiConn.getAccessToken()
            cutoff = now + timedelta(seconds=apiConn.getTokenExpiresIn())
            request.session['auth0_token_expire'] = time.mktime(cutoff.timetuple())
        return apiConn


    def __init__(self, acc_token=None):
        """create connection using parameters from settings
        Args:
            acc_token: str/None if None, a new token will be requested
        """
        self.token = None # dict
        if not acc_token:
            get_token = GetToken(settings.AUTH0_DOMAIN)
            # returns dict with keys: access_token, scope, expires_in, token_type
            # token[expires_in] = 86400 (24 hrs)
            token = get_token.client_credentials(
                    settings.AUTH0_MGMT_CLIENTID,
                    settings.AUTH0_MGMT_SECRET,
                    API_URL)
            acc_token = token['access_token']
            self.token = token
        self.conn = Auth0(settings.AUTH0_DOMAIN, acc_token)

    def getAccessToken(self):
        if self.token:
            return self.token['access_token']

    def getTokenExpiresIn(self):
        """Returns: int number of seconds"""
        if self.token:
            return self.token['expires_in']

    def getUsers(self):
        """Get all users
        Returns: list of dicts
        """
        list_kwargs = {
                'page': 0,
                'per_page': 25,
                'sort':"created_at:-1",
                'include_totals': True
        }
        users = []
        cur_total = 0
        # returns a dict w. keys: start, length, total, limit, users
        data = self.conn.users.list(**list_kwargs)
        users.extend(data['users'])
        logger.debug('Start:{start} Length:{length} Total:{total} Limit:{limit}'.format(**data))
        num_total = data['total']
        cur_total += data['length']
        while (cur_total < num_total):
            list_kwargs['page'] += 1
            data = self.conn.users.list(**list_kwargs)
            users.extend(data['users'])
            cur_total += data['length']
        return users

    def syncVerified(self, users):
        """Sync profile.verified with data from users
        Args:
            users: list of dicts from getUsers
        Returns: int - number of profiles updated
        """
        num_upd = 0
        for d in users:
            try:
                profile = Profile.objects.get(socialId=d['user_id'])
            except Profile.DoesNotExist:
                logger.warning('Profile does not exist for user_id: {user_id}'.format(**d))
            else:
                ev = d.get('email_verified', None)
                if ev is not None and ev != profile.verified:
                    profile.verified = bool(ev)
                    profile.save(update_fields=('verified',))
                    num_upd += 1
        return num_upd

    def make_initial_pass(self, email, year_joined):
        prefx = email.split('@')[0]
        p = "{0}.{1}!".format(prefx, year_joined)
        logger.debug('{0}={1}'.format(email, p))
        return p

    def findUserByEmail(self, email):
        """Returns user_id or None if not found"""
        qterm = "email:{0}".format(email)
        data = self.conn.users.list(q=qterm, search_engine='v2')
        if 'users' in data and len(data['users']) > 0:
            result = data['users'][0]
            return result['user_id']
        return None

    def createUser(self, email, password, verify_email=True):
        """Create new user account
        Returns: str auth0 userid
        """
        ev = not verify_email
        body = {
            'connection': DEFAULT_CONN_NAME,
            'email': email,
            'password': password,
            'email_verified': ev,
            'verify_email': verify_email,
        }
        response = self.conn.users.create(body)
        return response['user_id']


    def updateUser(self, user_id, email, verify_email=True):
        """Update email of an existing user account
        Note: cannot update username (auth0 will do it), get 400 error:
            Auth0Error: Cannot update username and email_verified simultaneously
        Args:
            user_id: str - auth0 user_id
            email: str - used as both username and email
        Returns: dict response object
        """
        ev = not verify_email
        body = {
            'connection': DEFAULT_CONN_NAME,
            'email': email,
            'verify_email': verify_email,
            'client_id': settings.AUTH0_MGMT_CLIENTID,
        }
        response = self.conn.users.update(user_id, body)
        return response
