# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-05-27 03:20
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0168_auto_20190514_1930'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionplan',
            name='cmeTags',
            field=models.ManyToManyField(blank=True, help_text='cmeTags to be added to profile for users on this plan', related_name='plans', to='users.CmeTag'),
        ),
        migrations.AlterField(
            model_name='signupemailpromo',
            name='first_year_discount',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='First billingCycle promotional discount (price and discount should not be specified together)', max_digits=5, null=True),
        ),
        migrations.AlterField(
            model_name='signupemailpromo',
            name='first_year_price',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='First billingCycle promotional price (price and discount should not be specified together)', max_digits=5, null=True),
        ),
    ]