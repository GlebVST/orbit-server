# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-02-21 01:53
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0012_auto_20170216_0316'),
    ]

    operations = [
        migrations.AlterField(
            model_name='usersubscription',
            name='display_status',
            field=models.CharField(choices=[('Trial', 'Trial'), ('Active', 'Active'), ('Active-Canceled', 'Active-Canceled'), ('Suspended', 'Suspended'), ('Expired', 'Expired'), ('Trial-Canceled', 'Trial-Canceled')], help_text='Status for UI display', max_length=40),
        ),
    ]
