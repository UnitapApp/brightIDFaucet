# Generated by Django 4.0.4 on 2023-11-30 14:21

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('faucet', '0064_merge_20231108_1331'),
    ]

    operations = [
        migrations.RenameField(
            model_name='claimreceipt',
            old_name='passive_address',
            new_name='to_address',
        ),
    ]