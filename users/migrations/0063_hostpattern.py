# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-10-11 00:18
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0062_eligiblesite_is_unlisted'),
    ]

    operations = [
        migrations.CreateModel(
            name='HostPattern',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('start_pattern', models.CharField(help_text='url pattern to test against path. No leading or trailing slash.', max_length=200)),
                ('use_exact_match', models.BooleanField(default=False, help_text='True if the url represented by host/pattern (exact match) is an allowed url.')),
                ('path_contains', models.CharField(blank=True, default='', help_text='If given, url path part must contain this term. No trailing slash.', max_length=200)),
                ('pattern_key', models.CharField(blank=True, default='', help_text='valid key in URL_PATTERNS dict', max_length=40)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['host', 'eligible_site', 'pattern_key', 'path_contains'],
                'db_table': 'trackers_hostpattern',
                'managed': False,
            },
        ),
    ]
