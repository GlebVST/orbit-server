from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from users.emailServiceProvider import MailchimpApi

# NOTE: Different ESPs could be implemented by creating a derived class and adding to this dictionary.
ESP_MAP = {"Mailchimp": MailchimpApi}
DEFAULT_ESP = "Mailchimp"


class Command(BaseCommand):
    help = 'Syncs User Profile fields to Email Service Provider'

    def add_arguments(self, parser):
        """Optional argument to specify Email Service Provider"""
        parser.add_argument(
            '--esp_name',
            type=str,
            help='Default Email Service Provider is declared in settings as '
                    'DEFAULT_EMAIL_SERVICE_PROVIDER. This is only necessary '
                    'if you want to sync to a different provider.'
            )

    def handle(self, *args, **options):
        esp_sync_class = None

        if options['esp_name']:
            esp_name = options['esp_name']
            self.stdout.write('esp_name %s provided' % (esp_name))
        else:
            try:
                esp_name = settings.SYNC_EMAIL_SERVICE_PROVIDER
            except AttributeError:
                esp_name = DEFAULT_ESP
            self.stdout.write('No Email Service Provider (ESP) name provided, using %s' % esp_name)

        esp_sync_class = ESP_MAP.get(esp_name)

        if esp_sync_class:
            esp_sync = esp_sync_class()
            ready = esp_sync.espIsReady()
            if ready:
                self.stdout.write('%s is ready to Sync' % esp_name)

                compared = esp_sync.compareData()
                if compared:
                    self.stdout.write('Local data has been compared to %s data' % esp_name)
                    self.stdout.write('%s new users to add' % str(len(esp_sync.toCreate)))
                    self.stdout.write('%s users to update' % str(len(esp_sync.toUpdate)))
                    self.stdout.write('%s users to remove' % str(len(esp_sync.toRemove)))

                    updated = esp_sync.updateEspContacts()
                    if updated:
                        self.stdout.write('%s has been updated. Sync is complete.' % esp_name)
                    else:
                        self.stdout.write('%s could NOT be updated. Please try again later' % esp_name)
        else:
            self.stdout.write('Please implement a synch flow for %s' % esp_name)
