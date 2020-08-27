# -*- coding: utf-8 -*-
# Generated by Django 1.11.21 on 2020-07-16 06:41
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0203_proxypattern'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionplan',
            name='allowArticleHistory',
            field=models.BooleanField(default=False, help_text="Enable Article History rail in plugin for users on this plan. This field is OR'd with the per-user assignment to the ArticleHistory group to decide the permission."),
        ),
        migrations.AlterField(
            model_name='subscriptionplan',
            name='allowArticleSearch',
            field=models.BooleanField(default=False, help_text="Enable Related Article rail in plugin for users on this plan. This field is OR'd with the per-user assignment to the RelatedArticle group to decide the permission."),
        ),
    ]