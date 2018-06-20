# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-06-19 19:55
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0117_signupemailpromo_display_label'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubscriptionPlanType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Name of plan type. Must be unique.', max_length=64, unique=True)),
                ('needs_payment_method', models.BooleanField(default=False, help_text='If true: requires payment method on signup to create a subscription.')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name='subscriptionplankey',
            name='use_free_plan',
            field=models.BooleanField(default=False, help_text='If true: expects an Individual Standard Plan assigned to it, to be used in place of the BT Standard Plan for signup'),
        ),
        migrations.AlterField(
            model_name='subscriptionplan',
            name='planId',
            field=models.CharField(help_text='Unique. No whitespace. If plan_type is Braintree, the planId must be in sync with the actual plan in Braintree', max_length=36, unique=True),
        ),
        migrations.AlterField(
            model_name='subscriptionplan',
            name='trialDays',
            field=models.IntegerField(default=0, help_text='Trial period in days'),
        ),
        migrations.AddField(
            model_name='subscriptionplan',
            name='plan_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='plans', to='users.SubscriptionPlanType'),
        ),
    ]
