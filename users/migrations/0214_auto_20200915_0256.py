# Generated by Django 2.2.15 on 2020-09-15 02:56

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0213_auto_20200903_0734'),
    ]

    operations = [
        migrations.CreateModel(
            name='DdxTopicBook',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(help_text='Ddx Topic Book name', max_length=80, unique=True)),
                ('description', models.TextField(blank=True, default='', help_text='Notes/description of this book')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'trackers_ddxtopicbook',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='DdxTopicCollection',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('probability', models.FloatField(default=0, help_text='Probability between 0 and 1 for this item in the collection', validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(1)])),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'trackers_ddxtopiccollection',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='DxTopic',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(help_text='Dx Topic name. Note: every Ddx topic is also an entry here.', max_length=1000)),
                ('lcname', models.CharField(help_text='Dx Topic name - all lowercased', max_length=1000)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'trackers_dxtopic',
                'ordering': ('-created',),
                'managed': False,
            },
        ),
        migrations.DeleteModel(
            name='DiffDiagnosis',
        ),
        migrations.DeleteModel(
            name='Topic',
        ),
        migrations.AlterField(
            model_name='eligiblesite',
            name='preferred_title_key',
            field=models.CharField(blank=True, default='', help_text='The title key name to use when extracting title from google search results. If not specified, will use title.', max_length=40),
        ),
    ]
