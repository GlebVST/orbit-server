# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-10-25 22:15
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0071_auto_20171024_0517'),
    ]

    operations = [
        migrations.AlterField(
            model_name='affiliatepayout',
            name='amount',
            field=models.DecimalField(decimal_places=2, help_text='per_user bonus paid to affiliate in USD.', max_digits=5),
        ),
        migrations.AlterField(
            model_name='batchpayout',
            name='amount',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Batch amount paid', max_digits=8),
            preserve_default=False,
        ),
    ]