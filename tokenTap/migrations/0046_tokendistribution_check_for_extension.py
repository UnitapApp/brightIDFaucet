# Generated by Django 4.0.4 on 2024-05-25 07:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tokenTap', '0045_alter_constraint_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='tokendistribution',
            name='check_for_extension',
            field=models.BooleanField(default=False),
        ),
    ]