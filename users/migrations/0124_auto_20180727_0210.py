# -*- coding: utf-8 -*-
# Generated by Django 1.11.14 on 2018-07-27 02:10
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0123_auto_20180725_2113'),
    ]

    operations = [
        migrations.AlterField(
            model_name='hospital',
            name='city',
            field=models.CharField(db_index=True, max_length=80),
        ),
        migrations.AlterField(
            model_name='hospital',
            name='display_name',
            field=models.CharField(help_text='Used for display', max_length=200),
        ),
    ]