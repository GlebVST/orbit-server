# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-02-08 23:33
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0010_auto_20170208_0327'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='document',
            name='uploadId',
        ),
        migrations.RemoveField(
            model_name='entry',
            name='uploadId',
        ),
        migrations.AddField(
            model_name='document',
            name='set_id',
            field=models.CharField(blank=True, help_text='Used to group an image and its thumbnail into a set', max_length=36),
        ),
    ]