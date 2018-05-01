import logging
from smtplib import SMTPException
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from dateutil.relativedelta import *
from users.models import Affiliate, BatchPayout, AffiliatePayout
from users.paypal import PayPalApi
from users.emailutils import sendAffiliateReportEmail, sendAfflConsolationEmail

logger = logging.getLogger('mgmt.affp')

PROGRAM_NAME = 'Orbit Associates Program'

class Command(BaseCommand):
    help = "Calculate total payout, and if non-zero, create BatchPayout for the grandTotal with one item per Affiliate. Call PayPalApi.makePayout and update AffiliatePayout instances"

    def add_arguments(self, parser):
        """Named optional argument for report_only"""
        parser.add_argument(
            '--report_only',
            action='store_true',
            dest='report_only',
            default=False,
            help='Only send email report, and any consolation emails if needed. Do not submit any payment'
        )

    def handle(self, *args, **options):
        paypalApi = PayPalApi(
                settings.PAYPAL_API_BASEURL,
                settings.PAYPAL_CLIENTID,
                settings.PAYPAL_SECRET)
        email_to = settings.SALES_EMAIL
        # affl.pk => {total:Decimal, pks:list of AffiliatePayout pkeyids}
        total_by_affl = AffiliatePayout.objects.calcTotalByAffiliate()
        now = timezone.now()
        sender_batch_id = now.strftime('%Y%m%d%H%M')
        startdate = now - relativedelta(months=1)
        monyr = startdate.strftime('%B %Y')
        print(monyr)
        grandTotal = 0
        items = []
        aff_pks = []
        for aff_pk in sorted(total_by_affl):
            affl = Affiliate.objects.get(pk=aff_pk)
            aff_pks.append(aff_pk)
            total = total_by_affl[aff_pk]['total']
            grandTotal += total
            num_convertees = len(total_by_affl[aff_pk]['pks'])
            note = "Earnings for {0} total referral(s) that converted to Active users through the {1} for {2}.".format(num_convertees, PROGRAM_NAME, monyr)
            if not options['report_only']:
                # one payout-item per affiliate with amount=total
                items.append({
                    'sender_item_id':sender_batch_id+':{0}'.format(aff_pk),
                    'amount':total,
                    'receiver': affl.paymentEmail,
                    'note': note
                })
                logger.debug('Affl {0.paymentEmail} earned: {1}'.format(affl, total))
        if options['report_only']:
            try:
                sendAffiliateReportEmail(total_by_affl, email_to)
            except SMTPException as e:
                logger.exception('sendAffiliateReportEmail to {0} failed'.format(email_to))
            else:
                logger.info('sendAffiliateReportEmail to {0} sent.'.format(email_to))
            # For any Affiliate who did not earn any payout in this interval, send consolation email
            if aff_pks:
                affls = Affiliate.objects.exclude(pk__in=aff_pks).order_by('paymentEmail')
            else:
                affls = Affiliate.objects.all().order_by('paymentEmail')
            for affl in affls:
                print('No payout for {0}'.format(affl))
                aff_email = affl.paymentEmail
                try:
                    sendAfflConsolationEmail(affl, monyr)
                except SMTPException as e:
                    logger.exception('Send Consolation Email to {0} failed'.format(aff_email))
                else:
                    logger.info('Consolation Email to {0} sent.'.format(aff_email))
        elif grandTotal:
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
                bp.delete()
            else:
                logger.info('received_sender_batch_id:{0} payout_batch_id: {1} status {2}'.format(recvd_sender_batch_id, payout_batch_id, batch_status))
                # update BatchPayout instance
                bp.payout_batch_id = payout_batch_id
                bp.status = batch_status
                bp.save()
                print(bp)
                # update AffiliatePayout instances: set batchpayout
                for aff_pk in total_by_affl:
                    pks = total_by_affl[aff_pk]['pks']
                    qset = AffiliatePayout.objects.filter(pk__in=pks)
                    for m in qset:
                        m.batchpayout = bp
                        m.save()
                        logger.info('Update afp {0.pk}'.format(m))
