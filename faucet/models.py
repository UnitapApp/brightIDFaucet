import binascii
import logging
import uuid
from datetime import datetime, timedelta

from bip_utils import Bip44, Bip44Coins
from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils import timezone
from encrypted_model_fields.fields import EncryptedCharField
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from authentication.models import UserProfile
from brightIDfaucet.settings import BRIGHT_ID_INTERFACE
from core.models import BigNumField, NetworkTypes
from faucet.faucet_manager.lnpay_client import LNPayClient


def get_cache_time(id):
    return int((float(int(id) % 25) / 25.0) * 180.0) + 180


class WalletAccount(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    private_key = EncryptedCharField(max_length=100)
    network_type = models.CharField(
        choices=NetworkTypes.networks, max_length=10, default=NetworkTypes.EVM
    )

    @property
    def address(self):
        try:
            node = Bip44.FromPrivateKey(
                binascii.unhexlify(self.private_key), Bip44Coins.ETHEREUM
            )
            return node.PublicKey().ToAddress()
        except:  # noqa: E722   #dont change this, somehow it creates a bug
            # if changed to Exception
            try:
                keypair = Keypair.from_base58_string(self.private_key)
                return str(keypair.pubkey())
            except:  # noqa: E722   #dont change this, somehow it creates a
                # bug if changed to Exception
                pass

    def __str__(self) -> str:
        return "%s - %s" % (self.name, self.address)

    @property
    def main_key(self):
        return self.private_key


class BrightUserManager(models.Manager):
    def get_or_create(self, address):
        try:
            return super().get_queryset().get(address=address)
        except BrightUser.DoesNotExist:
            _user = BrightUser(address=address, _sponsored=True)

            # if it's debug save the object
            if settings.DEBUG:
                _user.save()
                return _user

            # don't create user if sponsorship fails
            # so user can retry connecting their wallet
            if BRIGHT_ID_INTERFACE.sponsor(str(_user.context_id)):
                _user.save()
                return _user


class BrightUser(models.Model):
    PENDING = "0"
    VERIFIED = "1"

    states = ((PENDING, "Pending"), (VERIFIED, "Verified"))

    address = models.CharField(max_length=45, unique=True)
    context_id = models.UUIDField(default=uuid.uuid4, unique=True)

    _verification_status = models.CharField(
        max_length=1, choices=states, default=PENDING
    )
    _last_verified_datetime = models.DateTimeField(
        default=timezone.make_aware(datetime.utcfromtimestamp(0))
    )
    _sponsored = models.BooleanField(default=False)

    objects = BrightUserManager()

    def __str__(self):
        return "%d - %s" % (self.pk, self.address)

    @property
    def verification_url(self, bright_interface=BRIGHT_ID_INTERFACE):
        return bright_interface.get_verification_link(str(self.context_id))

    @property
    def verification_status(self):
        _now = timezone.now()
        _delta = _now - self._last_verified_datetime
        _max_delta = timedelta(days=7)

        if self._verification_status == self.VERIFIED and _delta <= _max_delta:
            return self.VERIFIED
        return self.get_verification_status()

    def get_verification_status(self) -> states:
        is_verified = BRIGHT_ID_INTERFACE.get_verification_status(str(self.context_id))
        if is_verified:
            self._verification_status = self.VERIFIED
            self._last_verified_datetime = timezone.now()
        else:
            self._verification_status = self.PENDING
        self.save()
        return self._verification_status

    def get_verification_url(self) -> str:
        return BRIGHT_ID_INTERFACE.get_verification_link(str(self.context_id))


class ClaimReceipt(models.Model):
    MAX_PENDING_DURATION = 5  # minutes
    PENDING = "Pending"
    VERIFIED = "Verified"
    REJECTED = "Rejected"
    PROCESSED_FOR_TOKENTAP = "Processed"
    PROCESSED_FOR_TOKENTAP_REJECT = "Processed_Rejected"

    states = (
        (PENDING, "Pending"),
        (VERIFIED, "Verified"),
        (REJECTED, "Rejected"),
        (PROCESSED_FOR_TOKENTAP, "Processed"),
        (PROCESSED_FOR_TOKENTAP_REJECT, "Processed_Rejected"),
    )

    chain = models.ForeignKey("Chain", related_name="claims", on_delete=models.PROTECT)
    user_profile = models.ForeignKey(
        UserProfile,
        related_name="claims",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        default=None,
    )

    bright_user = models.ForeignKey(
        BrightUser,
        related_name="claims",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    _status = models.CharField(max_length=30, choices=states, default=PENDING)

    passive_address = models.CharField(max_length=512, null=True, blank=True)

    amount = BigNumField()
    datetime = models.DateTimeField()
    last_updated = models.DateTimeField(auto_now=True, null=True, blank=True)
    batch = models.ForeignKey(
        "TransactionBatch",
        related_name="claims",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )

    def status(self):
        return self._status

    @property
    def age(self):
        return timezone.now() - self.datetime

    @property
    def tx_hash(self):
        if self.batch:
            return self.batch.tx_hash
        return None

    @staticmethod
    def claims_count():
        cached_count = cache.get("gastap_claims_count")
        if cached_count:
            return cached_count
        count = ClaimReceipt.objects.filter(
            _status__in=[ClaimReceipt.VERIFIED, BrightUser.VERIFIED]
        ).count()
        cache.set("gastap_claims_count", count, 600)
        return count


class Chain(models.Model):
    chain_name = models.CharField(max_length=255)
    chain_id = models.CharField(max_length=255, unique=True)

    native_currency_name = models.CharField(max_length=255)
    symbol = models.CharField(max_length=255)
    decimals = models.IntegerField(default=18)

    explorer_url = models.URLField(max_length=255, blank=True, null=True)
    explorer_api_url = models.URLField(max_length=255, blank=True, null=True)
    explorer_api_key = models.CharField(max_length=255, blank=True, null=True)
    rpc_url = models.URLField(max_length=255, blank=True, null=True)
    logo_url = models.URLField(max_length=255, blank=True, null=True)
    modal_url = models.URLField(max_length=255, blank=True, null=True)
    gas_image_url = models.URLField(max_length=255, blank=True, null=True)
    rpc_url_private = models.URLField(max_length=255)

    max_claim_amount = BigNumField()

    poa = models.BooleanField(default=False)

    fund_manager_address = models.CharField(max_length=255)
    tokentap_contract_address = models.CharField(max_length=255, null=True, blank=True)

    wallet = models.ForeignKey(
        WalletAccount, related_name="chains", on_delete=models.PROTECT
    )

    max_gas_price = models.BigIntegerField(default=250000000000)
    gas_multiplier = models.FloatField(default=1)
    enough_fee_multiplier = models.BigIntegerField(default=200000)

    needs_funding = models.BooleanField(default=False)
    is_testnet = models.BooleanField(default=False)
    chain_type = models.CharField(
        max_length=10, choices=NetworkTypes.networks, default=NetworkTypes.EVM
    )
    order = models.IntegerField(default=0)

    is_one_time_claim = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    show_in_gastap = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.chain_name} - {self.pk} - {self.symbol}:{self.chain_id}"

    @property
    def has_enough_funds(self):
        if self.get_manager_balance() > self.max_claim_amount * 8:  # TODO check here
            return True
        logging.warning(f"Chain {self.chain_name} has insufficient funds in contract")
        return False

    @property
    def block_scan_address(self):
        address = ""
        if not self.explorer_url:
            return None
        if self.explorer_url[-1] == "/":
            address = self.explorer_url + f"address/{self.fund_manager_address}"
        else:
            address = self.explorer_url + f"/address/{self.fund_manager_address}"
        return address

    @property
    def manager_balance(self):
        return self.get_manager_balance()

    def get_manager_balance(self):
        if not self.rpc_url_private:
            return 0

        try:
            from faucet.faucet_manager.fund_manager import (
                EVMFundManager,
                SolanaFundManager,
            )

            if self.chain_type == NetworkTypes.EVM or int(self.chain_id) == 500:
                # if self.chain_id == 500:
                #     logging.debug("chain XDC NONEVM is checking its balances")
                funds = EVMFundManager(self).get_balance(self.fund_manager_address)
                return funds

            elif self.chain_type == NetworkTypes.SOLANA:
                fund_manager = SolanaFundManager(self)
                v = fund_manager.w3.get_balance(fund_manager.lock_account_address).value
                return v
            elif self.chain_type == NetworkTypes.LIGHTNING:
                lnpay_client = LNPayClient(
                    self.rpc_url_private,
                    self.wallet.main_key,
                    self.fund_manager_address,
                )
                return lnpay_client.get_balance()

            raise Exception("Invalid chain type")
        except Exception as e:
            logging.exception(
                f"Error getting manager balance for {self.chain_name} error is {e}"
            )
            return 0

    @property
    def wallet_balance(self):
        return self.get_wallet_balance()

    def get_wallet_balance(self):
        if not self.rpc_url_private:
            return 0

        try:
            from faucet.faucet_manager.fund_manager import (
                EVMFundManager,
                SolanaFundManager,
            )

            if self.chain_type == NetworkTypes.EVM or int(self.chain_id) == 500:
                return EVMFundManager(self).get_balance(self.wallet.address)
            elif self.chain_type == NetworkTypes.SOLANA:
                fund_manager = SolanaFundManager(self)
                v = fund_manager.w3.get_balance(
                    Pubkey.from_string(self.wallet.address)
                ).value
                return v
            elif self.chain_type == NetworkTypes.LIGHTNING:
                lnpay_client = LNPayClient(
                    self.rpc_url_private,
                    self.wallet.main_key,
                    self.fund_manager_address,
                )
                return lnpay_client.get_balance()
            raise Exception("Invalid chain type")
        except Exception as e:
            logging.exception(
                f"Error getting wallet balance for {self.chain_name} error is {e}"
            )
            return 0

    @property
    def has_enough_fees(self):
        if self.get_wallet_balance() > self.gas_price * self.enough_fee_multiplier:
            return True
        logging.warning(f"Chain {self.chain_name} has insufficient fees in wallet")
        return False

    @property
    def gas_price(self):
        if not self.rpc_url_private:
            return self.max_gas_price + 1

        try:
            from faucet.faucet_manager.fund_manager import EVMFundManager

            return EVMFundManager(self).get_gas_price()
        except:  # noqa: E722
            logging.exception(f"Error getting gas price for {self.chain_name}")
            return self.max_gas_price + 1

    @property
    def is_gas_price_too_high(self):
        if not self.rpc_url_private:
            return True

        try:
            from faucet.faucet_manager.fund_manager import EVMFundManager

            return EVMFundManager(self).is_gas_price_too_high
        except Exception:  # noqa: E722
            logging.exception(f"Error getting gas price for {self.chain_name}")
            return True

    @property
    def total_claims(self):
        cached_total_claims = cache.get(f"gas_tap_chain_total_claims_{self.pk}")
        if cached_total_claims:
            return cached_total_claims
        total_claims = ClaimReceipt.objects.filter(
            chain=self, _status__in=[ClaimReceipt.VERIFIED, BrightUser.VERIFIED]
        ).count()
        cache.set(
            f"gas_tap_chain_total_claims_{self.pk}",
            total_claims,
            get_cache_time(self.pk),
        )
        return total_claims

    @property
    def total_claims_this_round(self):
        cached_total_claims_this_round = cache.get(
            f"gas_tap_chain_total_claims_this_round_{self.pk}"
        )
        if cached_total_claims_this_round:
            return cached_total_claims_this_round
        from faucet.faucet_manager.claim_manager import RoundCreditStrategy

        total_claims_this_round = ClaimReceipt.objects.filter(
            chain=self,
            datetime__gte=RoundCreditStrategy.get_start_of_the_round(),
            _status__in=[ClaimReceipt.VERIFIED],
        ).count()
        cache.set(
            f"gas_tap_chain_total_claims_this_round_{self.pk}",
            total_claims_this_round,
            get_cache_time(self.pk),
        )
        return total_claims_this_round

    @property
    def total_claims_since_last_round(self):
        cached_total_claims_since_last_round = cache.get(
            f"gas_tap_chain_total_claims_since_last_round_{self.pk}"
        )
        if cached_total_claims_since_last_round:
            return cached_total_claims_since_last_round
        from faucet.faucet_manager.claim_manager import RoundCreditStrategy

        total_claims_since_last_round = ClaimReceipt.objects.filter(
            chain=self,
            datetime__gte=RoundCreditStrategy.get_start_of_previous_round(),
            _status__in=[ClaimReceipt.VERIFIED],
        ).count()
        cache.set(
            f"gas_tap_chain_total_claims_since_last_round_{self.pk}",
            total_claims_since_last_round,
            get_cache_time(self.pk),
        )
        return total_claims_since_last_round


class GlobalSettings(models.Model):
    gastap_round_claim_limit = models.IntegerField(default=5)
    tokentap_round_claim_limit = models.IntegerField(default=3)
    prizetap_round_claim_limit = models.IntegerField(default=3)
    is_gas_tap_available = models.BooleanField(default=True)


class TransactionBatch(models.Model):
    chain = models.ForeignKey(
        Chain, related_name="batches", on_delete=models.PROTECT, db_index=True
    )
    datetime = models.DateTimeField(auto_now_add=True)
    tx_hash = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    _status = models.CharField(
        max_length=30,
        choices=ClaimReceipt.states,
        default=ClaimReceipt.PENDING,
        db_index=True,
    )

    updating = models.BooleanField(default=False)

    @property
    def claims_count(self):
        return self.claims.count()

    @property
    def claims_amount(self):
        return sum([c.amount for c in self.claims.all()]) / 1e18

    @property
    def age(self):
        return timezone.now() - self.datetime

    @property
    def should_be_processed(self):
        return all(
            [
                self._status == ClaimReceipt.PENDING,
                not self.tx_hash,
            ]
        )

    @property
    def status_should_be_updated(self):
        return all(
            [
                self._status == ClaimReceipt.PENDING,
                self.tx_hash is not None,
            ]
        )

    @property
    def is_expired(self):
        return self.age > timedelta(minutes=ClaimReceipt.MAX_PENDING_DURATION)


class LightningConfig(models.Model):
    period = models.IntegerField(default=64800)
    period_max_cap = models.BigIntegerField()
    claimed_amount = models.BigIntegerField(default=0)
    current_round = models.IntegerField(null=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


class DonationReceipt(models.Model):
    states = (
        (ClaimReceipt.PENDING, "Pending"),
        (ClaimReceipt.VERIFIED, "Verified"),
        (ClaimReceipt.REJECTED, "Rejected"),
    )
    user_profile = models.ForeignKey(
        UserProfile,
        related_name="donations",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
    )
    tx_hash = models.CharField(max_length=255, blank=False, null=False)
    chain = models.ForeignKey(
        Chain,
        related_name="donation",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
    )
    value = models.CharField(max_length=255, null=True, blank=True)
    total_price = models.CharField(max_length=255, null=True, blank=True)
    datetime = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=30,
        choices=states,
        default=ClaimReceipt.PENDING,
    )

    class Meta:
        unique_together = ("chain", "tx_hash")
