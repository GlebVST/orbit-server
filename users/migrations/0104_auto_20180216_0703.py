# -*- coding: utf-8 -*-
# Generated by Django 1.11.10 on 2018-02-16 07:03
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0103_auto_20180215_0701'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionplan',
            name='display_name',
            field=models.CharField(default='Standard', help_text='Display name - what the user sees (e.g. Standard).', max_length=40),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='subscriptionplan',
            name='name',
            field=models.CharField(help_text='Internal Plan name (alphanumeric only). Must match value in Braintree. Will be used to set planId.', max_length=80),
        ),
    ]
