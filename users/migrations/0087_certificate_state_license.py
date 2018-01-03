# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-11-15 04:09
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0086_auto_20171115_0155'),
    ]

    operations = [
        migrations.AddField(
            model_name='certificate',
            name='state_license',
            field=models.ForeignKey(default=None, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='certificates', to='users.StateLicense'),
        ),
    ]