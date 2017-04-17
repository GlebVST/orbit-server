# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-04-17 20:52
from __future__ import unicode_literals

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0026_userfeedback_reviewed'),
    ]

    operations = [
        migrations.AddField(
            model_name='sponsor',
            name='abbrev',
            field=models.CharField(default='TUSM', max_length=10, unique=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='customer',
            name='customerId',
            field=models.UUIDField(default=uuid.uuid4, editable=False, help_text='Used for BT customerId', unique=True),
        ),
    ]
