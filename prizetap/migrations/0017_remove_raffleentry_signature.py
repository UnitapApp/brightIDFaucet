# Generated by Django 4.0.4 on 2023-08-15 06:40

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('prizetap', '0016_remove_raffle_signer'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='raffleentry',
            name='signature',
        ),
    ]
