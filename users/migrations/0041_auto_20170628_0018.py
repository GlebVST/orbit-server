# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-06-28 00:18
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0040_subscriptiontransaction_failure_alert_sent'),
    ]

    operations = [
        migrations.AddField(
            model_name='practicespecialty',
            name='is_primary',
            field=models.BooleanField(default=False, help_text='True if this is a Primary Specialty Certificate'),
        ),
        migrations.AddField(
            model_name='practicespecialty',
            name='parent',
            field=models.ForeignKey(help_text='If this entry is a sub-specialty, then specify its GeneralCert parent.', null=True, on_delete=django.db.models.deletion.CASCADE, to='users.PracticeSpecialty'),
        ),
    ]
