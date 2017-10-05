# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-10-04 05:19
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0061_subscriptiontransaction_trans_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='eligiblesite',
            name='is_unlisted',
            field=models.BooleanField(default=False, help_text='True if site should be unlisted'),
        ),
    ]
