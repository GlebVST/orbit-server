# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-03-11 00:45
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0019_certificate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='certificate',
            name='credits',
            field=models.DecimalField(decimal_places=2, max_digits=6),
        ),
        migrations.AlterField(
            model_name='certificate',
            name='name',
            field=models.CharField(help_text='Name on certificate', max_length=255),
        ),
        migrations.AlterField(
            model_name='certificate',
            name='referenceId',
            field=models.CharField(blank=True, default=None, help_text='alphanum unique key generated from the certificate id', max_length=64, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='profile',
            name='inviteId',
            field=models.CharField(max_length=36, unique=True),
        ),
    ]
