# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-06-16 00:01
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0038_auto_20170615_2333'),
    ]

    operations = [
        migrations.AddField(
            model_name='practicespecialty',
            name='is_abms_board',
            field=models.BooleanField(default=False, help_text='True if this is an ABMS Board/General Cert'),
        ),
    ]
