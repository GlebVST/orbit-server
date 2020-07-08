# -*- coding: utf-8 -*-
# Generated by Django 1.11.21 on 2020-07-08 01:19
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0201_auto_20200626_0125'),
    ]

    operations = [
        migrations.AddField(
            model_name='eligiblesite',
            name='page_title_prefix',
            field=models.CharField(blank=True, default='', help_text='Common prefix in page titles will be stripped from the offer description.', max_length=100),
        ),
        migrations.AddField(
            model_name='eligiblesite',
            name='strip_title_after',
            field=models.CharField(blank=True, default='', help_text='Strip all characters from the page title after the given term. (e.g. the pipe symbol: |). Used for sites like Nature.', max_length=60),
        ),
        migrations.AlterField(
            model_name='eligiblesite',
            name='page_title_suffix',
            field=models.CharField(blank=True, default='', help_text='Common suffix in page titles will be stripped from the offer description.', max_length=100),
        ),
        migrations.AlterField(
            model_name='subscriptionplan',
            name='allowArticleSearch',
            field=models.BooleanField(default=False, help_text="Enable Related Article rail in plugin for users on this plan. This field is OR'd with the per-profile allowArticleSearch to decide the permission."),
        ),
    ]
