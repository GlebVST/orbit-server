# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-12-12 07:38
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0095_storycme'),
    ]

    operations = [
        migrations.AlterField(
            model_name='storycme',
            name='story',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='storycme', to='users.Story'),
        ),
    ]