from __future__ import unicode_literals
import logging
import re
from datetime import timezone
from time import sleep
from io import StringIO
from dateutil.parser import parse as dparse
from django.core.management import BaseCommand
from django.db import transaction, IntegrityError

from users.models import Profile
from users.models.residents import OrbitProcedure, Case, OrbitProcedureMatch

logger = logging.getLogger('mgmt.csv')

class Command(BaseCommand):
    help = "Process Case logs table to establish matches between facility procedure names and Orbit case types."

    def add_arguments(self, parser):
        parser.add_argument('--facility', dest='facility', help='Facility to process', default=None)
        parser.add_argument('--force_match', dest='force_match', help='Force re-matching for cases that have Orbit procedure assigned already', default=False)

    def handle(self, *args, **options):
        force_match = options['force_match']
        facility = options['facility']
        Case.objects.re_match(facility, force_match)