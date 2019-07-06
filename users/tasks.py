"""Celery tasks for users app"""
import logging
from celery import shared_task
from django.utils import timezone
from .models import *

logger = logging.getLogger('gen.tasks')

@shared_task
def add(x, y):
    """For debugging"""
    #print('add {0} + {1}'.format(x,y))
    return x + y
