from auth0.v3.authentication import GetToken
from auth0.v3.management import Auth0
from django.conf import settings
import os

# from .env file
client_id = os.environ['ORBIT_AUTH0_MGMT_CLIENTID']
client_secret = os.environ['ORBIT_AUTH0_MGMT_CLIENT_SECRET']

def connect():
    domain = settings.AUTH0_DOMAIN
    mgmt_url = 'https://{0}/api/v2/'.format(domain)
    get_token = GetToken(domain)
    # returns dict with keys: access_token, scope, expires_in, token_type
    token = get_token.client_credentials(client_id, client_secret, mgmt_url)
    acc_token = token['access_token']
    conn = Auth0(domain, acc_token)
    return conn


def listUsers(conn):
    """Print all users"""
    data = conn.users.list()     # returns a dict w. keys: start, length, total, limit, users
    print('Start:{start} Length:{length} Total:{total} Limit:{limit}'.format(**data))
    users = data['users']
    for d in users:
        print("{email: <35} v:{email_verified: <4} id:{user_id: <25} last_login:{last_login}".format(**d))
    return users
