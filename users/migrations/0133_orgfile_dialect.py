# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-08-20 23:20
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0132_auto_20180820_2056'),
    ]

    operations = [
        migrations.AddField(
            model_name='orgfile',
            name='dialect',
            field=models.CharField(blank=True, help_text='dialect of file for csv processing', max_length=40),
        ),
    ]