# -*- coding: utf-8 -*-
# Generated by Django 1.11.21 on 2020-02-18 03:37
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('users', '0190_auto_20200207_0703'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrgEnrollee',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('firstName', models.CharField(max_length=30)),
                ('lastName', models.CharField(max_length=30)),
                ('middleName', models.CharField(max_length=30)),
                ('lcFullName', models.CharField(help_text='lowercase fullname whitespace removed', max_length=60)),
                ('npiNumber', models.CharField(blank=True, help_text='Professional ID', max_length=20)),
                ('planName', models.CharField(blank=True, default='', help_text='Set to plan name when user subscribes to an Individual Plan', max_length=80)),
                ('enrollDate', models.DateTimeField(blank=True, help_text='Set when user subscribes to individual plan', null=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('group', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orgenrollees', to='users.OrgGroup')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orgenrollees', to='users.Organization')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='orgenrollees', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='orgenrollee',
            unique_together=set([('organization', 'npiNumber', 'lastName')]),
        ),
    ]
