# Generated by Django 3.0.6 on 2020-05-11 04:33

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='task',
            old_name='descripiton',
            new_name='description',
        ),
    ]
