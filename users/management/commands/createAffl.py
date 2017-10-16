import logging
from hashids import Hashids
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from users.models import User, Profile, Affiliate

logger = logging.getLogger('mgmt.newaffl')

class Command(BaseCommand):
    help = "Create an Affiliate instance for the args: userid, payment_email, bonus"

    def add_arguments(self, parser):
        # positional arguments
        parser.add_argument('user_id', type=int)
        parser.add_argument('payment_email')
        parser.add_argument('bonus', type=float)

    def handle(self, *args, **options):
        user_id = options['user_id']
        payment_email = options['payment_email']
        bonus = options['bonus']
        if not bonus or bonus < 0:
            raise ValueError('Invalid bonus')
        user = User.objects.get(pk=user_id)
        profile = user.profile # ensure user has a profile instance
        qset = Affiliate.objects.filter(user=user)
        if qset.exists():
            raise ValueError('Affiliate already exists for user: {0}'.format(user))
            return
        # using default alphabet of [a-zA-Z0-9]
        hashgen = Hashids(salt=settings.HASHIDS_SALT, min_length=5)
        affid = hashgen.encode(user.pk)
        m = Affiliate.objects.create(
                user=user,
                affiliateId=affid,
                paymentEmail=payment_email,
                bonus=bonus)
        profile.is_affiliate = True
        profile.save()
        msg = 'Created Affiliate instance for user {0} with affiliateId: {1.affiliateId} PaymentEmail: {1.paymentEmail} and bonus={1.bonus}'.format(user, m)
        logger.info(msg)
        print(msg)
