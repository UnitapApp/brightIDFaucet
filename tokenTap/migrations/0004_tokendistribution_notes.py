# Generated by Django 4.0.4 on 2023-05-12 08:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tokenTap', '0003_tokendistribution_max_number_of_claims'),
    ]

    operations = [
        migrations.AddField(
            model_name='tokendistribution',
            name='notes',
            field=models.TextField(blank=True, null=True),
        ),
    ]
