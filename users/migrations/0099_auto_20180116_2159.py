# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2018-01-16 21:59
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0098_auto_20180109_0206'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubscriptionEmail',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('billingCycle', models.PositiveIntegerField()),
                ('remind_renew_sent', models.BooleanField(default=False, help_text='set to True upon sending of renewal reminder email')),
                ('expire_alert_sent', models.BooleanField(default=False, help_text='set to True upon sending of card expiry alert email')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.RemoveField(
            model_name='usersubscription',
            name='remindRenewSent',
        ),
        migrations.AddField(
            model_name='usersubscription',
            name='next_plan',
            field=models.ForeignKey(default=None, help_text='Used to store plan for pending downgrade', null=True, on_delete=django.db.models.deletion.CASCADE, to='users.SubscriptionPlan'),
        ),
        migrations.AddField(
            model_name='subscriptionemail',
            name='subscription',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscriptionemails', to='users.UserSubscription'),
        ),
        migrations.AlterUniqueTogether(
            name='subscriptionemail',
            unique_together=set([('subscription', 'billingCycle')]),
        ),
    ]