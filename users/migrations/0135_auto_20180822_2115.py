# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-08-22 21:15
from __future__ import unicode_literals

from django.db import migrations, models
import users.models.base


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0134_auto_20180822_0106'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='orgfile',
            name='dialect',
        ),
        migrations.AddField(
            model_name='orgfile',
            name='csvfile',
            field=models.FileField(blank=True, help_text='If original document is not in plain-text CSV, then upload converted file here', null=True, upload_to=users.models.base.orgfile_document_path),
        ),
        migrations.AddField(
            model_name='orgmember',
            name='setPasswordEmailSent',
            field=models.BooleanField(default=False, help_text='Set to True when password-ticket email is sent'),
        ),
        migrations.AddField(
            model_name='subspecialty',
            name='cmeTags',
            field=models.ManyToManyField(blank=True, help_text='Applicable cmeTags', related_name='subspecialties', to='users.CmeTag'),
        ),
        migrations.AlterField(
            model_name='orgfile',
            name='content_type',
            field=models.CharField(blank=True, help_text='document content_type', max_length=100),
        ),
        migrations.AlterField(
            model_name='orgfile',
            name='document',
            field=models.FileField(help_text='Original document uploaded by user', upload_to=users.models.base.orgfile_document_path),
        ),
        migrations.AlterField(
            model_name='orgfile',
            name='name',
            field=models.CharField(blank=True, help_text='document file name', max_length=255),
        ),
    ]