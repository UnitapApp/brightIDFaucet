# Generated by Django 4.0.4 on 2023-11-22 05:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tokenTap', '0021_alter_constraint_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='constraint',
            name='explanation',
            field=models.TextField(blank=True, null=True),
        ),
    ]