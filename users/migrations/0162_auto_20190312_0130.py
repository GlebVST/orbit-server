# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-03-12 01:30
from __future__ import unicode_literals

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0161_orgmember_snapshotdate'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='activateGoals',
            field=models.BooleanField(default=True, help_text='If True: goal compliance checking is enabled for members of this enterprise org.'),
        ),
        migrations.AlterField(
            model_name='orgmember',
            name='snapshot',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default='', help_text='A snapshot of the goals status for this user. It is computed by a management command run periodically.'),
        ),
    ]