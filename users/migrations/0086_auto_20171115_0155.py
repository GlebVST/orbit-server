# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-11-15 01:55
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0085_state_rncertvalid'),
    ]

    operations = [
        migrations.RenameField(
            model_name='state',
            old_name='rncertValid',
            new_name='rnCertValid',
        ),
    ]
