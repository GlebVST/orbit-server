# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-03-02 06:13
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0016_auto_20170222_0227'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='browsercmeoffer',
            options={'permissions': (('view_offer', 'Can view BrowserCmeOffer'),), 'verbose_name_plural': 'BrowserCME Offers'},
        ),
        migrations.AlterModelOptions(
            name='entry',
            options={'permissions': (('view_feed', 'Can view Feed'), ('view_dashboard', 'Can view Dashboard'), ('post_brcme', 'Can redeem BrowserCmeOffer'), ('post_srcme', 'Can post Self-reported Cme entry'), ('print_audit_report', 'Can print/share audit report'), ('print_brcme_cert', 'Can print/share BrowserCme certificate')), 'verbose_name_plural': 'Entries'},
        ),
        migrations.RemoveField(
            model_name='eligiblesite',
            name='domain_url',
        ),
        migrations.RemoveField(
            model_name='eligiblesite',
            name='is_valid_domurl',
        ),
        migrations.AddField(
            model_name='eligiblesite',
            name='domain_name',
            field=models.CharField(default='wikipedia.org', help_text='wikipedia.org', max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='profile',
            name='cmeDuedate',
            field=models.DateTimeField(help_text='Due date for CME requirements fulfillment', null=True),
        ),
        migrations.AlterField(
            model_name='eligiblesite',
            name='domain_title',
            field=models.CharField(help_text='e.g. Wikipedia Anatomy Pages', max_length=300, unique=True),
        ),
        migrations.AlterField(
            model_name='eligiblesite',
            name='is_valid_expurl',
            field=models.BooleanField(default=True, help_text='Is example_url a valid URL'),
        ),
    ]