# -*- coding: utf-8 -*-
# Generated by Django 1.11.18 on 2019-01-07 20:59
from __future__ import unicode_literals

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0150_auto_20181213_0144'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityLog',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('valid', models.BooleanField(default=True)),
                ('x_tracking_seconds', models.PositiveIntegerField()),
                ('browser_extensions', django.contrib.postgres.fields.jsonb.JSONField(blank=True)),
                ('num_highlight', models.PositiveIntegerField(default=0)),
                ('num_mouse_click', models.PositiveIntegerField(default=0)),
                ('num_mouse_move', models.PositiveIntegerField(default=0)),
                ('num_start_scroll', models.PositiveIntegerField(default=0)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'trackers_activitylog',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='ActivitySet',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('total_tracking_seconds', models.PositiveIntegerField(help_text='Sum of x_tracking_seconds over a set of logs')),
                ('computed_value', models.DecimalField(decimal_places=2, help_text='Total number of engaged seconds', max_digits=9)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'trackers_activityset',
                'managed': False,
            },
        ),
        migrations.AddField(
            model_name='subscriptionplan',
            name='organization',
            field=models.ForeignKey(blank=True, help_text='Used to assign an enterprise plan to a particular Organization', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='plans', to='users.Organization'),
        ),
        migrations.AlterField(
            model_name='subscriptionplan',
            name='plan_key',
            field=models.ForeignKey(blank=True, help_text='Used to group Individual plans for the pricing pages', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='plans', to='users.SubscriptionPlanKey'),
        ),
    ]
