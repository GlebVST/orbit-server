# -*- coding: utf-8 -*-
# Generated by Django 1.11.21 on 2019-10-07 04:07
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0179_auto_20190926_1954'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='cmetag',
            options={'ordering': ['priority', 'name'], 'verbose_name_plural': 'CME Tags'},
        ),
        migrations.AlterField(
            model_name='cmetag',
            name='priority',
            field=models.IntegerField(default=2, help_text='Used for non-alphabetical sort. 0=Specialty-name tag. 1=SA-CME. 2=Others.'),
        ),
        migrations.AlterField(
            model_name='subscriptionplan',
            name='max_trial_credits',
            field=models.DecimalField(decimal_places=1, default=0, help_text='Maximum OrbitCME credits allowed in Trial period. -1 means: no redeeming allowed in Trial. 0 means: use default max_trial_credits in settings.py. A positive value: overrides default value in settings.py', max_digits=3),
        ),
    ]