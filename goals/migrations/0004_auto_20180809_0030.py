# -*- coding: utf-8 -*-
# Generated by Django 1.11.14 on 2018-08-09 00:30
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('goals', '0003_remove_licensegoal_interval'),
    ]

    operations = [
        migrations.CreateModel(
            name='CmeBaseGoal',
            fields=[
            ],
            options={
                'proxy': True,
                'verbose_name_plural': 'CME-Goals',
                'indexes': [],
            },
            bases=('goals.basegoal',),
        ),
        migrations.CreateModel(
            name='LicenseBaseGoal',
            fields=[
            ],
            options={
                'proxy': True,
                'verbose_name_plural': 'License-Goals',
                'indexes': [],
            },
            bases=('goals.basegoal',),
        ),
        migrations.RemoveField(
            model_name='cmegoal',
            name='dueDateType',
        ),
        migrations.RemoveField(
            model_name='wellnessgoal',
            name='dueDateType',
        ),
        migrations.AddField(
            model_name='basegoal',
            name='dueDateType',
            field=models.IntegerField(choices=[(0, 'One-off. Due immediately'), (1, 'Recurring at set interval. Due on fixed MM/DD'), (2, 'Recurring at set interval. Due at any time counting back over interval'), (3, 'Recurring at set interval. Due on user birth date'), (4, 'Recurring at set interval. Due on license expiration date')], default=0),
            preserve_default=False,
        ),
    ]
