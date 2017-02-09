# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2017-01-24 00:49
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_subscriptionplan_usersubscription'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='subscriptionplan',
            name='active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='usersubscription',
            name='display_status',
            field=models.CharField(blank=True, help_text='Status for UI display', max_length=40),
        ),
        migrations.AlterField(
            model_name='usersubscription',
            name='status',
            field=models.CharField(blank=True, choices=[('Active', 'Active'), ('Canceled', 'Canceled'), ('Expired', 'Expired'), ('Past Due', 'Past Due'), ('Pending', 'Pending')], help_text='Braintree-defined status', max_length=10),
        ),
    ]