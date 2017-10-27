import logging
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from users.models import Affiliate, BatchPayout, AffiliatePayout
from users.paypal import PayPalApi

logger = logging.getLogger('mgmt.updafp')

class Command(BaseCommand):
    help = "Get incomplete BatchPayouts and call PayPalApi to get their status and update db, including payout item status"

    def handle(self, *args, **options):
        paypalApi = PayPalApi(
                settings.PAYPAL_API_BASEURL,
                settings.PAYPAL_CLIENTID,
                settings.PAYPAL_SECRET)
        batch_payouts = BatchPayout.objects.filter(date_completed__isnull=True).order_by('created')
        for bp in batch_payouts:
            logger.debug('Check status for BatchPayout {0.pk}/{0.payout_batch_id}'.format(bp))
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
            aff_payouts_by_email = dict() # email:list
            for m in aff_payouts:
                aff_email = m.affiliate.paymentEmail
                aff_payouts_by_email.setdefault(aff_email, []).append(m)
            # update aff_payouts from items
            items = data['items']
            with transaction.atomic():
                for d in items:
                    # one payout-item can correspond to multiple AffiliatePayout model instances (multiple convertees are summed into 1 item)
                    aff_email = d['payout_item']['receiver']
                    afps = aff_payouts_by_email.get(aff_email, [])
                    if not afps:
                        logger.warning('No AffiliatePayout instances found for payment_item_email: {0}'.format(aff_email))
                        continue
                    for m in afps:
                        logger.debug('Updating afp {0.pk} for {1}'.format(m, aff_email))
                        m.payoutItemId = d['payout_item_id']
                        m.status = d['transaction_status']
                        if 'transactionId' in d:
                            m.transactionId = d['transactionId']
                        m.save()
                        logger.info('Updated afp {0.pk}/{0}'.format(m))
                        if 'errors' in d:
                            err = d['errors']
                            msg = err['name'] + ': ' + err['message']
                            logger.warning('Error for afp {0.pk}/{0}: {1}'.format(m, msg))
                bp.status = batch_status
                bp.date_completed = date_completed
                bp.save()
                logger.info('Updated BatchPayout {0.pk}/{0}'.format(bp))
