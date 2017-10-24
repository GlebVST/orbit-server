import logging
import requests
import json
from datetime import timedelta
from pprint import pprint
from django.utils import timezone

MAX_NUM_ITEMS = 500
SERVICE_TOKEN = 'oauth2/token'
SERVICE_PAYOUT = 'payments/payouts'
SERVICE_PAYOUT_ITEM = 'payments/payouts-item'

logger = logging.getLogger('gen.ppal')

class PayPalApi(object):

    def __init__(self, baseurl, clientid, secret, token=None):
        self.BASEURL = baseurl
        self.token = token
        self.clientid = clientid
        self.secret = secret

    def getToken(self):
        """Example data response
        {u'access_token': u'A21AAHE0YoqnAAlTXKezDwkn_...',
        u'app_id': u'APP-80W284485P519543T',
        u'expires_in': 32400,
        u'nonce': u'2017-10-20T03:24:08ZQRiQax34Js9m37LpWe5APjjNALSoFn6ZTu0amIg9meY',
        u'scope': u'https://api.paypal.com/v1/payments/.* openid https://uri.paypal.com/payments/payouts',
        u'token_type': u'Bearer'
        }
        """
        payload = {'grant_type': 'client_credentials'}
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US",
        }
        now = timezone.now()
        service = self.BASEURL + SERVICE_TOKEN
        r = requests.post(
                service,
                data=payload,
                headers=headers,
                auth=(self.clientid, self.secret)
        )
        data = r.json()
        data['created'] = now # add extra key for reference point for expires_in
        logger.debug('Token {access_token} expires in {expires_in} seconds starting from {created_at}'.format(**data))
        logger.debug(data['scope'])
        self.token = data

    def getOrRenewToken(self):
        if not self.token:
            self.getToken()
            return self.token['access_token']
        now = timezone.now()
        cutoff = now + timedelta(seconds=60)
        created = self.token['created']
        esecs = self.token['expires_in']
        expires = created + timedelta(seconds=esecs)
        if now >= expires:
            logger.debug('Getting new token')
            self.getToken()
        return self.token['access_token']


    def makePayout(self, sender_batch_id, email_subject, items):
        if not items:
            return None
        if len(items) > MAX_NUM_ITEMS:
            raise ValueError('Maximum number of items exceeded.')
        access_token = self.getOrRenewToken()
        headers = {
            "Accept": "application/json",
            'Content-Type': 'application/json',
            "Authorization": "Bearer "+access_token,
        }
        payload = {
            "sender_batch_header": {
                "sender_batch_id": sender_batch_id,
                "email_subject": email_subject,
                "recipient_type": 'EMAIL'
            },
            'items': []
        }
        for d in items:
            payload['items'].append({
                "amount": {
                    "value": str(d['amount']),
                    "currency": "USD"
                },
                "sender_item_id": d['sender_item_id'],
                "receiver": d['receiver'], # an email address
                "note": "Thank you"
            })
        #pprint(payload)
        service = self.BASEURL + SERVICE_PAYOUT
        r = requests.post(
                service,
                data=json.dumps(payload),
                headers=headers)
        logger.debug('status: {0.status_code}'.format(r))
        if r.status_code != 201:
            logger.warning(r.text)
            raise ValueError('Bad status code: {0.status_code}'.format(r))
        data = r.json()
        bh = data['batch_header']
        recvd_sbid = bh['sender_batch_header']['sender_batch_id']
        payout_batch_id = bh['payout_batch_id']
        batch_status = bh['batch_status']
        return (recvd_sbid, payout_batch_id, batch_status)

    def getPayoutStatus(self, payout_batch_id):
        """Request status of a batch payout"""
        access_token = self.getOrRenewToken()
        headers = {
            "Accept": "application/json",
            "Authorization": "Bearer "+access_token,
        }
        service = self.BASEURL + SERVICE_PAYOUT + '/' + payout_batch_id
        r = requests.get(service, headers=headers)
        data = r.json()
        #pprint(data)
        return data

    def getPayoutItemStatus(self, payout_item_id):
        """Request status of a payout item"""
        access_token = self.getOrRenewToken()
        headers = {
            "Accept": "application/json",
            "Authorization": "Bearer "+access_token,
        }
        service = self.BASEURL + SERVICE_PAYOUT_ITEM + '/' + payout_item_id
        r = requests.get(service, headers=headers)
        data = r.json()
        #pprint(data)
        return data
