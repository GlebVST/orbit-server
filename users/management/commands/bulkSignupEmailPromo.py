import logging
import csv
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from users.models import User, UserSubscription, SignupEmailPromo

logger = logging.getLogger('mgmt.bsep')

DISCOUNT = 'discount'
FINAL_PRICE = 'final-price'
DEFAULT_DISPLAY_LABEL = 'Orbit Signup Promotion'

fieldNames = (
    'email address',
    'dollar_value',
    'type',
    'display_label'
)

class Command(BaseCommand):
    help="Create SignupEmailPromo for the emails in the input csv file. Expected columns in the file are: email, dollar_value, type. Where type is either discount or final-price."

    def add_arguments(self, parser):
        parser.add_argument('filepath',
            help="Filepath of the csv file to read")

    def handle(self, *args, **options):
        fpath = options['filepath']
        try:
            f = open(fpath, 'rb')
        except IOError as e:
            self.stdout.write('Invalid filepath: {filepath}'.format(**options))
            return
        else:
            reader = csv.DictReader(f,
                fieldnames=fieldNames,
                restkey='extra', dialect='excel')
            all_data = [row for row in reader]
            raw_data = all_data[1:]
            f.close()
            num_created = 0
            for d in raw_data:
                email = d['email address'].lower()
                if not email:
                    continue
                if d['type'] not in (DISCOUNT, FINAL_PRICE):
                    msg = "Invalid type for {email address}: {type}".format(**d)
                    self.stdout.write(msg)
                    return # exit
                promo_label = d['display_label']
                if not promo_label:
                    promo_label = DEFAULT_DISPLAY_LABEL
                dollar_value = Decimal(d['dollar_value'])
                # check if promo already exists for this email (casei)
                sep = SignupEmailPromo.objects.get_casei(email)
                if sep:
                    if sep.display_label != promo_label:
                        sep.display_label = promo_label
                    if d['type'] == DISCOUNT:
                        sep.first_year_discount = dollar_value
                        sep.first_year_price = None
                    elif d['type'] == FINAL_PRICE:
                        sep.first_year_price = dollar_value
                        sep.first_year_discount = None
                    sep.save()
                    msg = 'Updated existing SignupEmailPromo: {0}.'.format(sep)
                    logger.info(msg)
                    self.stdout.write(msg)
                    continue
                # check if user subs already exists for this email (casei)
                qs = UserSubscription.objects.select_related('user').filter(user__email__iexact=email).order_by('-created')
                if qs.exists():
                    us = qs[0]
                    if us.display_status != UserSubscription.UI_TRIAL_CANCELED:
                        msg = '! UserSubscription already exists for {0.user}|{0} with status: {0.display_status}. Skip to next line.'.format(us)
                        logger.info(msg)
                        self.stdout.write(msg)
                        continue
                # create model instance
                if d['type'] == DISCOUNT:
                    sep = SignupEmailPromo.objects.create(email=email, first_year_discount=dollar_value, display_label=promo_label)
                else:
                    sep = SignupEmailPromo.objects.create(email=email, first_year_price=dollar_value, display_label=promo_label)
                msg = "Created SignupEmailPromo {0}".format(sep)
                logger.info(msg)
                ##self.stdout.write(msg)
                num_created += 1
            msg = "Total number of entries created: {0}".format(num_created)
            logger.info(msg)
            self.stdout.write(msg)
