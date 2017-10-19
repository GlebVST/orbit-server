from auth0.v3.authentication import GetToken
from auth0.v3.management import Auth0
from django.conf import settings
import os
from users.models import Profile

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
    list_kwargs = {
            'page': 0,
            'per_page': 25,
            'sort':"created_at:-1",
            'include_totals': True
    }
    users = []
    cur_total = 0
    data = conn.users.list(**list_kwargs)     # returns a dict w. keys: start, length, total, limit, users
    users.extend(data['users'])
    print('Start:{start} Length:{length} Total:{total} Limit:{limit}'.format(**data))
    num_total = data['total']
    cur_total += data['length']
    while (cur_total < num_total):
        list_kwargs['page'] += 1
        print('Requesting page {page}'.format(**list_kwargs))
        data = conn.users.list(**list_kwargs)     # returns a dict w. keys: start, length, total, limit, users
        users.extend(data['users'])
        print('Start:{start} Length:{length} Total:{total} Limit:{limit}'.format(**data))
        cur_total += data['length']
    print('{0} users:'.format(cur_total))
    for d in users:
        if 'last_login' not in d:
            d['last_login'] = None
        print("{email: <35} v:{email_verified: <4} id:{user_id: <25} last_login:{last_login}".format(**d))
        try:
            profile = Profile.objects.get(socialId=d['user_id'])
        except Profile.DoesNotExist:
            print('Profile does not exist for user_id: {user_id}'.format(**d))
        else:
            ev = d.get('email_verified', None)
            if ev is not None and ev != profile.verified:
                profile.verified = bool(ev)
                print('Updated verified to: {0.verified}'.format(profile))
                profile.save()
    return users
