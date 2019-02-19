# -*- coding: utf-8 -*-
# Generated by Django 1.11.18 on 2019-01-15 03:27
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0151_auto_20190107_2059'),
        ('goals', '0014_auto_20181109_0124'),
    ]

    operations = [
        migrations.AddField(
            model_name='basegoal',
            name='subspecialties',
            field=models.ManyToManyField(blank=True, help_text='Applicable sub-specialties. If selected, they must be sub-specialties of the chosen PracticeSpecialties above. No selection means any', related_name='basegoals', to='users.SubSpecialty'),
        ),
        migrations.AddField(
            model_name='cmegoal',
            name='creditTypes',
            field=models.ManyToManyField(blank=True, help_text='Eligible creditTypes that satisfy this goal.', related_name='cmegoals', to='users.CreditType'),
        ),
        migrations.AddField(
            model_name='cmegoal',
            name='mapNullTagToSpecialty',
            field=models.BooleanField(default=False, help_text="If True, null value for cmeTag in goal definition means the UserGoal will have tag set to the user's specialty. Otherwise null cmeTag means Any Topic."),
        ),
        migrations.AlterField(
            model_name='basegoal',
            name='degrees',
            field=models.ManyToManyField(blank=True, help_text='Applicable primary roles. No selection means any', related_name='basegoals', to='users.Degree'),
        ),
        migrations.AlterField(
            model_name='basegoal',
            name='specialties',
            field=models.ManyToManyField(blank=True, help_text='Applicable specialties. No selection means any', related_name='basegoals', to='users.PracticeSpecialty'),
        ),
        migrations.AlterField(
            model_name='cmegoal',
            name='cmeTag',
            field=models.ForeignKey(blank=True, help_text='Null value means tag is either user specialty or Any Topic (see mapNullTagToSpecialty)', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='cmegoals', to='users.CmeTag'),
        ),
    ]
