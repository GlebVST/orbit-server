# -*- coding: utf-8 -*-
# Generated by Django 1.11.18 on 2019-01-16 06:48
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0153_auto_20190115_2158'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='cmetag',
            name='notes',
        ),
        migrations.AddField(
            model_name='cmetag',
            name='instructions',
            field=models.TextField(default='', help_text='Instructions to provider. May contain Markdown-formatted text.'),
        ),
        migrations.AlterField(
            model_name='cmetag',
            name='name',
            field=models.CharField(help_text='Short-form name. Used in tag button', max_length=80, unique=True),
        ),
    ]
