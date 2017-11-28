# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-11-27 23:13
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0089_auto_20171121_0637'),
    ]

    operations = [
        migrations.CreateModel(
            name='LicenseType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=10, unique=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name='statelicense',
            name='license_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='statelicenses', to='users.LicenseType'),
        ),
    ]
