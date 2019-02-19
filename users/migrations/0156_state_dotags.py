# -*- coding: utf-8 -*-
# Generated by Django 1.11.18 on 2019-01-21 21:47
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0155_auto_20190119_0146'),
    ]

    operations = [
        migrations.AddField(
            model_name='state',
            name='doTags',
            field=models.ManyToManyField(blank=True, help_text='cmeTags to be added to profile for users with DO degree', related_name='dostates', to='users.CmeTag'),
        ),
    ]
