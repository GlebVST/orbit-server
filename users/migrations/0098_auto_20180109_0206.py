# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2018-01-09 02:06
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0097_auto_20180108_2159'),
    ]

    operations = [
        migrations.AlterField(
            model_name='usersubscription',
            name='display_status',
            field=models.CharField(choices=[('Trial', 'Trial'), ('Active', 'Active'), ('Active-Canceled', 'Active-Canceled'), ('Suspended', 'Suspended'), ('Expired', 'Expired'), ('Trial-Canceled', 'Trial-Canceled'), ('Active-Downgrade-Scheduled', 'Active-Downgrade-Scheduled')], help_text='Status for UI display', max_length=40),
        ),
    ]
