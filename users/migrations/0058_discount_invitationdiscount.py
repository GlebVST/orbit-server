# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-08-28 06:50
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0008_alter_user_username_max_length'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('users', '0057_browsercmeoffer_valid'),
    ]

    operations = [
        migrations.CreateModel(
            name='Discount',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('discountId', models.CharField(max_length=36, unique=True)),
                ('name', models.CharField(max_length=80)),
                ('amount', models.DecimalField(decimal_places=2, help_text=' in USD', max_digits=5)),
                ('numBillingCycles', models.IntegerField(default=1, help_text='Number of Billing Cycles')),
                ('activeInvitee', models.BooleanField(default=False, help_text='True if this is the current active invitee discount')),
                ('activeInviter', models.BooleanField(default=False, help_text='True if this is the current active inviter discount')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='InvitationDiscount',
            fields=[
                ('invitee', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to=settings.AUTH_USER_MODEL)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('inviteeDiscount', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inviteediscounts', to='users.Discount')),
                ('inviter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inviters', to=settings.AUTH_USER_MODEL)),
                ('inviterDiscount', models.ForeignKey(help_text='Set when inviter subscription has been updated with the discount', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='inviterdiscounts', to='users.Discount')),
            ],
        ),
    ]
