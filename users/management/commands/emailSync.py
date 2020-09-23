import logging
from collections import OrderedDict
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from users.email_service_provider import MailchimpApi

logger = logging.getLogger('mgmt.mailc')

# NOTE: Different ESPs could be implemented by creating a derived class and adding to this dictionary.
ESP_MAP = OrderedDict({"Mailchimp": MailchimpApi})


class Command(BaseCommand):
    help = 'Syncs User Profile fields to Email Service Provider'

    def add_arguments(self, parser):
        """Optional argument to specify Email Service Provider"""
        parser.add_argument(
            '--esp_name',
            type=str,
            help='Default Email Service Provider is declared in settings as '
                    'DEFAULT_ESP. esp_name is only necessary '
                    'if you want to sync to a different provider.'
            )

    def handle(self, *args, **options):
        esp_sync_class = None

        if options['esp_name']:
            esp_name = options['esp_name']
            self.stdout.write('esp_name %s provided' % (esp_name))
        else:
            try:
                esp_name = settings.DEFAULT_ESP
                self.stdout.write('Using default ESP %s' % esp_name)
            except AttributeError:
                # If nothing is supplied, use first in ESP_MAP
                esp_name = ESP_MAP.keys()[0]
                self.stdout.write('No Email Service Provider (ESP) name provided, using %s' % esp_name)

        try:
            esp_sync_class = ESP_MAP[esp_name]
            esp_sync = esp_sync_class()
            ready = esp_sync.espIsReady()
            if ready:
                self.stdout.write('%s is ready to Sync' % esp_name)
                compared = esp_sync.compareData()
                if compared:
                    msg = "Local data has been compared to {0} data".format(esp_name)
                    self.stdout.write(msg)
                    logger.info(msg)
                    msg = "Num new users to add: {0}".format(len(esp_sync.toCreate))
                    self.stdout.write(msg)
                    logger.info(msg)
                    msg = "Num users to update: {0}".format(len(esp_sync.toUpdate))
                    self.stdout.write(msg)
                    logger.info(msg)
                    msg = "Num users to remove: {0}".format(len(esp_sync.toRemove))
                    self.stdout.write(msg)
                    logger.info(msg)
                    if len(esp_sync.incompleteData) > 0:
                        msg = "! {0} users have incomplete data and could not be synced".format(len(esp_sync.incompleteData))
                        self.stdout.write(msg)
                        logger.warning(msg)

                    updated = esp_sync.updateEspContacts()
                    if updated:
                        msg = "{0} has been updated. Sync is complete.".format(esp_name)
                        self.stdout.write(msg)
                        logger.info(msg)
                    else:
                        msg = "[MailChimp emailSync] {0} could NOT be updated. Please try again later.".format(esp_name)
                        self.stdout.write(msg)
                        logger.error(msg)
        except Exception as e:
            logger.exception('MailChimp emailSync fatal exception')
