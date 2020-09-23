# Generated by Django 2.2.15 on 2020-09-16 01:35

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0215_auto_20200915_0626'),
    ]

    operations = [
        migrations.AddField(
            model_name='uitab',
            name='icon_1x',
            field=models.CharField(blank=True, default='', help_text='Tab icon 1x relative path', max_length=500),
        ),
        migrations.AddField(
            model_name='uitab',
            name='icon_2x',
            field=models.CharField(blank=True, default='', help_text='Tab icon 2x relative path', max_length=500),
        ),
        migrations.AddField(
            model_name='uitab',
            name='icon_3x',
            field=models.CharField(blank=True, default='', help_text='Tab icon 3x relative path', max_length=500),
        ),
        migrations.AlterField(
            model_name='uitab',
            name='contents',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict, help_text='JSON object that represents the contents of the tab. See existing tabs as a guide.'),
        ),
    ]
