import json
import os
import jwt
import requests
import logging
from django.contrib.auth import authenticate
from django.conf import settings

logger = logging.getLogger('gen.jwt')

def jwt_get_username_from_payload_handler(payload):
    """Example payload using token obtained from a Machine-to-Machine API
        {
          'iss': 'https://orbit-dev.auth0.com/',
          'sub': '9A8qdQltnfm65z1TjA0xWES64dNmq8Ap@clients',
          'aud': 'https://orbit-dev/new-orbit-api',
          'iat': 1596519738,
          'exp': 1596606138,
          'azp': '9A8qdQltnfm65z1TjA0xWES64dNmq8Ap',
          'gty': 'client-credentials'
        }
    """
    logger.info(str(payload))
    username = payload.get('sub').replace('|', '.')
    if username == '9A8qdQltnfm65z1TjA0xWES64dNmq8Ap@clients':
        username='faria@orbitcme.com'
    user_dict = dict(username=username, email=username)
    user = authenticate(request=None, remote_user=user_dict)
    print('jwt_get_username_from_payload authenticate: {0}'.format(user))
    return username


def jwt_decode_token(token):
    header = jwt.get_unverified_header(token)
    auth0_domain = settings.AUTH0_DOMAIN
    jwks = requests.get('https://{}/.well-known/jwks.json'.format(auth0_domain)).json()
    public_key = None
    for jwk in jwks['keys']:
        if jwk['kid'] == header['kid']:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))

    if public_key is None:
        raise Exception('jwt_decode_token Error: Public key not found.')

    api_identifier = os.environ.get('API_IDENTIFIER')
    issuer = 'https://{}/'.format(auth0_domain)
    return jwt.decode(token, public_key, audience=settings.AUTH0_AUDIENCE, issuer=issuer, algorithms=['RS256'])


def get_token_auth_header(request):
    """Obtains the access token from the Authorization Header
    """
    auth = request.META.get("HTTP_AUTHORIZATION", None)
    parts = auth.split()
    token = parts[1]
    print('get_token_auth_header: {0}'.format(token))
    return token


def decode_token(token):
    """Decode verified token and return decoded dict"""
    return jwt.decode(token, verify=False)
