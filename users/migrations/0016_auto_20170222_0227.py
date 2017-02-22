# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-02-22 02:27
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0015_auto_20170221_0328'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='browsercmeoffer',
            options={'verbose_name_plural': 'BrowserCME Offers'},
        ),
        migrations.AlterModelOptions(
            name='entry',
            options={'verbose_name_plural': 'Entries'},
        ),
        migrations.AddField(
            model_name='browsercmeoffer',
            name='sponsor',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.PROTECT, to='users.Sponsor'),
            preserve_default=False,
        ),
    ]
