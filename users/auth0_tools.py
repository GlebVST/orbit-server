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
PSUFIX = 'AjMAVYQgiOgeS4Kwijb6ejHTzsMNsqvsauMIooVlxkOA'

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
        now_ts = now.timestamp() # <float>
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
            request.session['auth0_token_expire'] = cutoff.timestamp()
        return apiConn


    def __init__(self, acc_token=None):
        """create connection using parameters from settings
        Args:
            acc_token: str/None if None, a new token will be requested
        Example token scope: (str containing all the available permissions)
            read:client_grants read:users update:users delete:users create:users
            read:users_app_metadata update:users_app_metadata delete:users_app_metadata create:users_app_metadata
        Most functions in this class require the above permissions.
        """
        self.token = None # dict
        if not acc_token:
            get_token = GetToken(settings.AUTH0_DOMAIN)
            # returns dict with keys: access_token, scope, expires_in, token_type
            # token[expires_in] = 86400 (24 hrs)
            token = get_token.client_credentials(
                    settings.AUTH0_MGMT_CLIENTID,
                    settings.AUTH0_MGMT_SECRET,
                    settings.AUTH0_MGMT_API)
            acc_token = token['access_token']
            self.token = token
            #logger.info("GetToken scope: {scope}".format(**token)) # to check scope
        self.conn = Auth0(settings.AUTH0_DOMAIN, acc_token)

    def getAccessToken(self):
        if self.token:
            return self.token['access_token']

    def getTokenExpiresIn(self):
        """Returns: int number of seconds"""
        if self.token:
            return self.token['expires_in']

    def getUsers(self, limit_total=None):
        """Get all users
        Args:
            limit_total: int/None limit number of users returned
        Returns: list of dicts
        """
        list_kwargs = {
                'page': 0,
                'per_page': 500,
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
        if not limit_total: # requested total
            limit_total = 10000000
        req_total = min(num_total, limit_total)
        # get more users until we reach min(num_total, limit_total)
        while (cur_total < req_total):
            list_kwargs['page'] += 1
            # throttle
            time.sleep(0.5) # to prevent Auth0Error: 429: Global limit has been reached
            data = self.conn.users.list(**list_kwargs)
            users.extend(data['users'])
            cur_total += data['length']
        return users

    def checkVerified(self, profiles):
        """Check auth0 email_verified for the given profiles and update profile if needed.
        Args:
            profiles: Profile queryset (e.g. profiles with verified=False)
        Returns: int - number of profiles updated
        """
        num_upd = 0
        for p in profiles:
            if not p.socialId:
                continue
            result = self.getUserDictForAuth0Id(p.socialId) # dict
            ev = result.get('email_verified', None)
            if ev is not None and ev != p.verified:
                p.verified = bool(ev)
                p.save(update_fields=('verified',))
                num_upd += 1
                logger.info("Updated verified for user {0.pk}".format(p))
            time.sleep(0.5) # to prevent Auth0Error: 429: Global limit has been reached
        return num_upd

    def make_initial_pass(self, email, date_joined):
        """Args:
            email: str
            date_joined: datetime
        Returns: str
        """
        #sufx = email.split('@')[0][::-1]
        p = "Z.{0:%Y%m%d%H%M%S}.{1}!".format(date_joined, PSUFIX)
        logger.debug('{0}={1}'.format(email, p))
        return p

    def getUserDictForAuth0Id(self, user_id):
        """Returns user result dict for the given auth0 user_id
        Returns: dict
        Example: {
            'created_at': '2020-09-23T14:33:14.817Z',
            'name': 'some@gmail.com',
            'nickname': 'some',
            'email': 'some@gmail.com',
            'email_verified': False,
            'identities': [{'connection': 'Username-Password-Authentication',
                'isSocial': False,
                'provider': 'auth0',
                'user_id': '5f6b5caa3810fa006f719db9'}
            ],
            'last_ip': '143.111.84.114',
            'last_login': '2020-10-09T17:51:15.343Z',
            'logins_count': 5,
            'picture': 'https://s.gravatar.com/avatar/some.png',
            'updated_at': '2020-10-09T17:51:15.343Z',
            'user_id': 'auth0|5f6b5caa3810fa006f719db9'}
        """
        qterm = "user_id:{0}".format(user_id)
        data = self.conn.users.list(q=qterm, search_engine='v2')
        if 'users' in data and len(data['users']) > 0:
            result = data['users'][0]
            return result
        return None

    def findUserByEmail(self, email):
        """Returns user_id or None if not found"""
        qterm = "email:{0}".format(email)
        data = self.conn.users.list(q=qterm, search_engine='v2')
        if 'users' in data and len(data['users']) > 0:
            result = data['users'][0]
            return result['user_id']
        return None

    def createUser(self, email, password, verify_email=False):
        """Create new user account
        Returns: str auth0 userid
        """
        body = {
            'connection': DEFAULT_CONN_NAME,
            'email': email,
            'password': password,
            'email_verified': False,
            'verify_email': verify_email,
        }
        response = self.conn.users.create(body)
        return response['user_id']


    def updateUser(self, user_id, email, verify_email=True):
        """Update email of an existing user account
        Note: we dont ask for separate username at signup, so here
          we update both name and email to the new email.
        Args:
            user_id: str - auth0 user_id
            email: str - used as both name and email
        Returns: dict response object
        """
        body = {
            'connection': DEFAULT_CONN_NAME,
            'name': email,
            'email': email,
            'email_verified': False,
            'verify_email': verify_email,
            'client_id': settings.AUTH0_MGMT_CLIENTID,
        }
        response = self.conn.users.update(user_id, body)
        return response

    def setEmailVerified(self, user_id):
        """Update email_verified of an existing user account
        Args:
            user_id: str - auth0 user_id
        Returns: dict response object
        """
        body = {
            'connection': DEFAULT_CONN_NAME,
            'email_verified': True,
        }
        response = self.conn.users.update(user_id, body)
        return response


    def change_password_ticket(self, user_id, redirect_url, ttl_days=30):
        """Create change_password_ticket
        Reference: https://auth0.com/docs/api/management/v2#!/Tickets/post_password_change
        Args:
            user_id: str auth0 userid
            redirect_url: URL - to redirect user to after ticket is used
            ttl_days: int number of days for which ticket url is valid
        Returns: URL of ticket
        """
        if ttl_days <= 0:
            raise ValueError('change_password_ticket: ttl_days must be a positive integer')
        body = {
            'user_id': user_id,
            'result_url': redirect_url,
            'ttl_sec': 86400*ttl_days
        }
        response = self.conn.tickets.create_pswd_change(body)
        return response['ticket']

