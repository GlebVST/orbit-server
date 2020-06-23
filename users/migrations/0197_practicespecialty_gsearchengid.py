# -*- coding: utf-8 -*-
# Generated by Django 1.11.21 on 2020-06-12 04:48
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0196_auto_20200528_2351'),
    ]

    operations = [
        migrations.AddField(
            model_name='practicespecialty',
            name='gsearchengid',
            field=models.CharField(blank=True, default='', help_text='Google search engine ID to use for this specialty. Must match a valid ID defined in the google console.', max_length=50),
        ),
    ]