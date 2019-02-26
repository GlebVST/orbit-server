# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-02-25 01:48
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0158_auto_20190218_0122'),
    ]

    operations = [
        migrations.AddField(
            model_name='usercmecredit',
            name='total_credits_earned',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Total lifetime credits earned by user.', max_digits=10),
        ),
        migrations.AlterField(
            model_name='usercmecredit',
            name='boost_credits',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Available credits from Boost purchases. Is added to plan_credits to get remaining_credits available.', max_digits=10),
        ),
        migrations.AlterField(
            model_name='usercmecredit',
            name='plan_credits',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Available credits offered by Plan. Value is deducted when user redeems offer', max_digits=10),
        ),
    ]
