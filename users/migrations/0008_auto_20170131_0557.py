# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-01-31 05:57
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_auto_20170131_0450'),
    ]

    operations = [
        migrations.DeleteModel(
            name='PointPurchaseOption',
        ),
        migrations.DeleteModel(
            name='PointRewardOption',
        ),
        migrations.RemoveField(
            model_name='pointtransaction',
            name='customer',
        ),
        migrations.RemoveField(
            model_name='pointtransaction',
            name='entry',
        ),
        migrations.RemoveField(
            model_name='browsercmeoffer',
            name='points',
        ),
        migrations.DeleteModel(
            name='PointTransaction',
        ),
    ]
