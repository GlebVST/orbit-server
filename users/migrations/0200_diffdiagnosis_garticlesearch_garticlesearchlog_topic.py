# -*- coding: utf-8 -*-
# Generated by Django 1.11.21 on 2020-06-24 07:03
from __future__ import unicode_literals

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0199_auto_20200623_0748'),
    ]

    operations = [
        migrations.CreateModel(
            name='DiffDiagnosis',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'trackers_diffdiagnosis',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='GArticleSearch',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('search_term', models.CharField(help_text='search term passed to the query', max_length=500)),
                ('gsearchengid', models.CharField(help_text='Google search engineid passed to the query', max_length=50)),
                ('results', django.contrib.postgres.fields.jsonb.JSONField(blank=True)),
                ('processed_results', django.contrib.postgres.fields.jsonb.JSONField(blank=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Google Article Search',
                'verbose_name_plural': 'Google Article Searches',
                'db_table': 'trackers_garticlesearch',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='GArticleSearchLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Google Article Search Log',
                'verbose_name_plural': 'Google Article Search Logs',
                'db_table': 'trackers_garticlesearchlog',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Topic',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Topic name', max_length=100)),
                ('lcname', models.CharField(help_text='Topic name - all lowercased', max_length=100)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'trackers_topic',
                'ordering': ('specialty', 'name'),
                'managed': False,
            },
        ),
    ]
