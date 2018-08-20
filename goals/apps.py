# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.apps import AppConfig

class GoalsConfig(AppConfig):
    name = 'goals'

    def ready(self):
        """Import signal_handlers submodule to connect the signals
        Reference: https://docs.djangoproject.com/en/1.11/topics/signals/
        """
        from .signal_handlers import handleProfileSaved
