import json
import jwt
import requests
import logging
from django.contrib.auth import authenticate
from django.conf import settings

logger = logging.getLogger('gen.jwt')

ISSUER = 'https://{}/'.format(settings.AUTH0_DOMAIN)
JWKS_URL = 'https://{}/.well-known/jwks.json'.format(settings.AUTH0_DOMAIN)

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
        Example payload from UI Lock
        {
            'iss': https://orbit-dev.auth0.com/,
            'sub': 'auth0|5906ccc95a90b615f9504a77',
            'aud': [https://orbit-dev/new-orbit-api’, https://orbit-dev.auth0.com/userinfo],
            'iat': 1596564441
            'exp': 1596571641,
            'azp': 'JNm7ns-4_ARJZA-Kz487V81ihb-48Qni',
            'scope': 'openid profile email',
        }
    Note: this has to return a non-empty str otherwise client gets invalid token error.
    """
    #logger.info(str(payload))
    user_id = payload.get('sub')
    user_dict = {'user_id': user_id}
    # This function does not take request as an arg, and so cannot pass it to authenticate!
    user = authenticate(request=None, remote_user=user_dict)
    logger.info('jwt_get_username_from_payload authenticate: {0}'.format(user))
    if user and user.email:
        return user.email # existing user (completed signup)
    return user_id # new user (just created, only has username set to user_id)

def jwt_decode_token(token):
    header = jwt.get_unverified_header(token)
    jwks = requests.get(JWKS_URL).json()
    public_key = None
    for jwk in jwks['keys']:
        if jwk['kid'] == header['kid']:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))

    if public_key is None:
        raise Exception('jwt_decode_token Error: Public key not found.')

    return jwt.decode(token, public_key, audience=settings.AUTH0_AUDIENCE, issuer=ISSUER, algorithms=['RS256'])


def get_token_auth_header(request):
    """Obtains the access token from the Authorization Header
    """
    auth = request.META.get("HTTP_AUTHORIZATION", None)
    #logger.info('get_token_auth_header: {0}'.format(auth))
    if auth:
        parts = auth.split()
        token = parts[1]
        return token
    return None

def decode_token(token):
    """Decode verified token and return decoded dict"""
    return jwt.decode(token, verify=False)
