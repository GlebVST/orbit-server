# -*- coding: utf-8 -*-
# Generated by Django 1.11.14 on 2018-08-08 07:04
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('goals', '0002_auto_20180808_0640'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='licensegoal',
            name='interval',
        ),
    ]