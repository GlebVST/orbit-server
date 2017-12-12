# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-12-11 17:14
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('users', '0090_auto_20171127_2313'),
    ]

    operations = [
        migrations.AlterField(
            model_name='statelicense',
            name='expiryDate',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='statelicense',
            name='license_no',
            field=models.CharField(blank=True, default='', help_text='License number', max_length=40),
        ),
        migrations.AlterField(
            model_name='statelicense',
            name='license_type',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, related_name='statelicenses', to='users.LicenseType'),
            preserve_default=False,
        ),
        migrations.AlterUniqueTogether(
            name='statelicense',
            unique_together=set([('user', 'state', 'license_type', 'license_no')]),
        ),
    ]
