# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-08-26 06:30
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0056_auto_20170818_1717'),
    ]

    operations = [
        migrations.AddField(
            model_name='browsercmeoffer',
            name='valid',
            field=models.BooleanField(default=True),
        ),
    ]
