# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-11-02 06:09
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0077_auto_20171102_0521'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='affiliate',
            name='discountLabel',
        ),
        migrations.AddField(
            model_name='affiliate',
            name='displayLabel',
            field=models.CharField(blank=True, default='', help_text='identifying label used in display', max_length=60),
        ),
        migrations.AlterField(
            model_name='profile',
            name='affiliateId',
            field=models.CharField(blank=True, default='', help_text='If conversion, specify Affiliate ID', max_length=20),
        ),
    ]
