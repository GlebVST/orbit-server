import logging
from datetime import datetime
from smtplib import SMTPException
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from users.models import Affiliate, BatchPayout, AffiliatePayout
from users.paypal import PayPalApi
from users.emailutils import sendAfflEarningsStatementEmail
import pytz
logger = logging.getLogger('mgmt.updafp')

class Command(BaseCommand):
    help = "Get that status for the given payout_batch_id and update the BatchPayout instance in the DB, including payout item status, and send earning statement emails to the Affiliates."

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('payout_batch_id')

    def handle(self, *args, **options):
        paypalApi = PayPalApi(
                settings.PAYPAL_API_BASEURL,
                settings.PAYPAL_CLIENTID,
                settings.PAYPAL_SECRET)
        pbid = options['payout_batch_id']
        bp = BatchPayout.objects.get(payout_batch_id=pbid)
        logger.info('Check status for BatchPayout {0.pk}/{0}'.format(bp))
        print('Check status for BatchPayout {0.pk}/{0}'.format(bp))
        data = paypalApi.getPayoutStatus(bp.payout_batch_id)
        bh = data['batch_header']
        batch_status = bh['batch_status']
        time_completed = bh['time_completed'] # str '2017-10-20T21:03:22Z'
        date_completed = None
        if time_completed:
            date_completed = timezone.make_aware(
                datetime.strptime(time_completed, '%Y-%m-%dT%H:%M:%SZ'),
                pytz.utc)

        aff_payouts = AffiliatePayout.objects.select_related('affiliate').filter(batchpayout=bp)
        aff_payouts_by_email = dict() # email:str => list of afp instances
        for m in aff_payouts:
            aff_email = m.affiliate.paymentEmail
            aff_payouts_by_email.setdefault(aff_email, []).append(m)
        # update aff_payouts from items
        items = data['items']
        if not bp.date_completed:
            with transaction.atomic():
                for d in items:
                    # 1 payout-item corresponds to 1+ AffiliatePayout model instances (1+ instances are summed into 1 item)
                    aff_email = d['payout_item']['receiver']
                    afps = aff_payouts_by_email.get(aff_email, [])
                    for m in afps:
                        logger.debug('Updating afp {0.pk} for {1}'.format(m, aff_email))
                        print('Updating afp {0.pk} for {1}'.format(m, aff_email))
                        m.payoutItemId = d['payout_item_id']
                        m.status = d['transaction_status']
                        if 'transaction_id' in d:
                            m.transactionId = d['transaction_id']
                        m.save()
                        logger.info('Updated afp {0.pk}/{0}'.format(m))
                        print('Updated afp {0.pk}/{0}'.format(m))
                bp.status = batch_status
                bp.date_completed = date_completed
                bp.save()
                logger.info('Updated BatchPayout {0.pk}/{0}'.format(bp))
                print('Updated BatchPayout {0.pk}/{0}'.format(bp))
        # prepare data for confirmation emails sent to each Affiliate
        for d in items:
            # 1 payout-item corresponds to 1+ AffiliatePayout model instances (1+ instances are summed into 1 item)
            aff_email = d['payout_item']['receiver']
            affl = Affiliate.objects.get(paymentEmail=aff_email)
            if 'errors' in d:
                err = d['errors']
                msg = err['name'] + ': ' + err['message']
                logger.warning('Error for item {0}: {1}'.format(aff_email, msg))
                print('Error for item {0}: {1}'.format(aff_email, msg))
                continue # do not send any confirmation email
            afps = aff_payouts_by_email.get(aff_email, [])
            if not afps:
                logger.warning('No AffiliatePayout instances found for payment_item_email: {0}'.format(aff_email))
                continue
            afp_data = [{
                'convertee': m.convertee,
                'amount': m.amount,
                'created': m.created
                } for m in afps]
            try:
                sendAfflEarningsStatementEmail(bp, affl, afp_data)
            except SMTPException as e:
                logger.exception('Send Confirmation Email to {0} failed'.format(aff_email))
            else:
                logger.info('Confirmation Email to {0} sent.'.format(aff_email))
                print('Confirmation Email to {0} sent.'.format(aff_email))
