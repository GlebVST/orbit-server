import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from users.models import Affiliate, UserSubscription, SubscriptionTransaction, AffiliatePayout
from users.paypal import PayPalApi

logger = logging.getLogger('mgmt.affp')

class Command(BaseCommand):
    help = "Calculate total amount earned by Affiliate, and create BatchPayout for the grandTotal if non-zero. Call PayPalApi.makePayout and update AffiliatePayout instances"

    def handle(self, *args, **options):
        paypalApi = PayPalApi(
                settings.PAYPAL_API_BASEURL,
                settings.PAYPAL_CLIENTID,
                settings.PAYPAL_SECRET)
        affl_by_pk = dict() # affl.pk => Affiliate instance
        grandTotal = 0
        items = []
        # affl.pk => {total:Decimal, pks:list of AffiliatePayout pkeyids}
        total_by_affl = AffiliatePayout.objects.calcTotalByAffiliate()
        now = timezone.now()
        sender_batch_id = now.strftime('%Y%m%d%H%M')
        for aff_pk in total_by_affl:
            affl = Affiliate.objects.get(pk=aff_pk)
            affl_by_pk[aff_pk] = affl
            total = total_by_affl[aff_pk]['total']
            grandTotal += total
            items.append({
                'sender_item_id':sender_batch_id+':'+str(aff_pk),
                'amount':total,
                'receiver': affl.paymentEmail
            })
            logger.info('Affl {0} earned: {1}'.format(affl, total))
        if grandTotal:
            now = timezone.now()
            bp = BatchPayout.objects.create(
                sender_batch_id = sender_batch_id,
                email_subject='Your earnings from the Orbit Associate Program',
                amount=grandTotal
            )
            logger.info('BatchPayout {0.pk}/{0} amount {0.amount}'.format(bp))

            try:
                (recvd_sender_batch_id, payout_batch_id, batch_status) = paypalApi.makePayout(sender_batch_id, bp.email_subject, items)
            except ValueError, e:
                logger.exception('makePayout error: {0}'.format(e))
            else:
                logger.info('received_sender_batch_id:{0} payout_batch_id: {1} status {2}'.format(recvd_sender_batch_id, payout_batch_id, batch_status))
                # update BatchPayout instance
                bp.payout_batch_id = payout_batch_id
                bp.status = batch_status
                bp.save()
                # update AffiliatePayout instances: set batchpayout
                for aff_pk in total_by_affl:
                    pks = total_by_affl[aff_pk]['pks']
                    qset = AffiliatePayout.objects.filter(pk__in=pks)
                    for m in qset:
                        m.batchpayout = bp
                        m.save()
                        logger.info('Update afp {0.pk}'.format(m))
