# Generated by Django 4.0.4 on 2023-02-28 12:22

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0004_alter_profile_initial_context_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='Wallet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('wallet_type', models.CharField(choices=[('EVM', 'EVM Wallet'), ('Solana', 'Solana Wallet'), ('Lightning', 'Lightning Wallet')], max_length=10)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wallets', to='authentication.profile')),
            ],
            options={
                'unique_together': {('wallet_type', 'profile')},
            },
        ),
        migrations.RemoveField(
            model_name='evmwallet',
            name='profile',
        ),
        migrations.RemoveField(
            model_name='solanawallet',
            name='profile',
        ),
        migrations.DeleteModel(
            name='BitcoinLightningWallet',
        ),
        migrations.DeleteModel(
            name='EVMWallet',
        ),
        migrations.DeleteModel(
            name='SolanaWallet',
        ),
    ]