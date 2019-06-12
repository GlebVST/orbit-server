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
        {'access_token': 'A21AAHE0YoqnAAlTXKezDwkn_...',
        'app_id': 'APP-80W284485P519543T',
        'expires_in': 32400,
        'nonce': '2017-10-20T03:24:08ZQRiQax34Js9m37LpWe5APjjNALSoFn6ZTu0amIg9meY',
        'scope': 'https://api.paypal.com/v1/payments/.* openid https://uri.paypal.com/payments/payouts',
        'token_type': 'Bearer'
        }
        """
        payload = {'grant_type': 'client_credentials'}
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US",
        }
        now = timezone.now()
        service = self.BASEURL + SERVICE_TOKEN
        print(service)
        r = requests.post(
                service,
                data=payload,
                headers=headers,
                auth=(self.clientid, self.secret)
        )
        data = r.json()
        data['created'] = now # add extra key for reference point for expires_in
        if 'access_token' in data:
            logger.info('Token {access_token} expires in {expires_in} seconds starting from {created}'.format(**data))
            #logger.debug(data['scope'])
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
            logger.info('Getting new token')
            self.getToken()
        return self.token['access_token']


    def makePayout(self, sender_batch_id, email_subject, items):
        """make POST request to BatchPayout API.
        Args:
        sender_batch_id:str for sender_batch_header
        email_subject:str email subject as seen by recipients
        items:list of dicts {amount,sender_item_id, receiver,note}
        Returns:tuple
        (recveived_sender_batch_id, payout_batch_id, batch_status)
        """
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
                "note": d['note']
            })
        pprint(payload)
        service = self.BASEURL + SERVICE_PAYOUT
        r = requests.post(
                service,
                data=json.dumps(payload),
                headers=headers)
        logger.info('status: {0.status_code}'.format(r))
        if r.status_code != 201:
            error_message = "makePayout: bad status code: {0.status_code}. Text: {0.text}".format(r)
            logger.warning(r)
            raise ValueError(error_message)
        data = r.json()
        bh = data['batch_header']
        recvd_sbid = bh['sender_batch_header']['sender_batch_id']
        payout_batch_id = bh['payout_batch_id']
        batch_status = bh['batch_status']
        return (recvd_sbid, payout_batch_id, batch_status)

    def getPayoutStatus(self, payout_batch_id):
        """Request status of a batch payout
        Example response:
        {
            'batch_header':
                {'amount': {'currency': 'USD', 'value': '5.25'},
                'batch_status': 'SUCCESS',
                'fees': {'currency': 'USD', 'value': '0.25'},
                'payout_batch_id': '6TVQTDH65LSNN',
                'sender_batch_header': {'email_subject': 'Another payout attempt',
                                        'sender_batch_id': '201710202102'},
                'time_completed': '2017-10-20T21:03:22Z',
                'time_created': '2017-10-20T21:02:57Z'
            },
            'items': [
                {'links': [
                    {
                        'encType': 'application/json',
                        'href': 'https://api.sandbox.paypal.com/v1/payments/payouts-item/R2WM3CAEQ336G';,
                        'method': 'GET',
                        'rel': 'item'
                    }
                ],
                'payout_batch_id': '6TVQTDH65LSNN',
                'payout_item': {
                    'amount': {'currency': 'USD', 'value': '5.25'},
                    'note': 'Thank yo',
                    'receiver': 'faria.chowdhury-buyer-1@gmail.com',
                    'recipient_type': 'EMAIL',
                    'sender_item_id': '201710202102:1'
                },
                'payout_item_fee': {'currency': 'USD', 'value': '0.25'},
                'payout_item_id': 'R2WM3CAEQ336G',
                'time_processed': '2017-10-20T21:03:15Z',
                'transaction_id': '3DL34442EM6673237',   -- key does not exist for failed transactions
                'transaction_status': 'SUCCESS',
                'errors': {'details, 'message', 'name'} -- key exists in case of errors
                }
            ],
        }
        """
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
