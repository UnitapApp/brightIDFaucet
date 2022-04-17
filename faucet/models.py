from django.db import models
import uuid
from encrypted_model_fields.fields import EncryptedCharField

from brightIDfaucet.settings import BRIGHT_ID_INTERFACE


class BrightUser(models.Model):
    PENDING = "0"
    VERIFIED = "1"

    states = ((PENDING, "Pending"),
              (VERIFIED, "Verified"))

    address = models.CharField(max_length=45, unique=True)
    context_id = models.UUIDField(default=uuid.uuid4, unique=True)

    _verification_status = models.CharField(max_length=1, choices=states, default=PENDING)

    @property
    def verification_url(self, bright_interface=BRIGHT_ID_INTERFACE):
        return bright_interface.get_verification_link(str(self.context_id))

    @property
    def verification_status(self):
        return self.get_verification_status()

    @staticmethod
    def get_or_create(address):
        try:
            return BrightUser.objects.get(address=address)
        except BrightUser.DoesNotExist:
            return BrightUser.objects.create(address=address)

    def get_verification_status(self, bright_interface=BRIGHT_ID_INTERFACE) -> states:
        if self._verification_status == self.VERIFIED:
            return self.VERIFIED

        is_verified = bright_interface.get_verification_status(str(self.context_id))

        if is_verified:
            self._verification_status = self.VERIFIED
            self.save()

        return self._verification_status

    def get_verification_url(self, bright_interface=BRIGHT_ID_INTERFACE) -> str:
        return bright_interface.get_verification_link(str(self.context_id))


class Chain(models.Model):
    name = models.CharField(max_length=255)
    symbol = models.CharField(max_length=255)
    chain_id = models.CharField(max_length=255, unique=True)
    rpc_url = models.URLField(max_length=255, blank=True, null=True)

    max_claim_amount = models.BigIntegerField()

    wallet_key = EncryptedCharField(max_length=100)

    def __str__(self):
        return f"{self.pk} - {self.symbol}:{self.chain_id}"


class ClaimReceipt(models.Model):
    MAX_PENDING_DURATION = 15  # minutes
    PENDING = '0'
    VERIFIED = '1'
    REJECTED = '2'

    states = ((PENDING, "Pending"),
              (VERIFIED, "Verified"),
              (REJECTED, "Rejected")
              )

    chain = models.ForeignKey(Chain, related_name="claims", on_delete=models.PROTECT)
    bright_user = models.ForeignKey(BrightUser, related_name="claims", on_delete=models.PROTECT)

    _status = models.CharField(max_length=1, choices=states, default=PENDING)

    amount = models.BigIntegerField()
    datetime = models.DateTimeField()
    tx_hash = models.CharField(max_length=100, blank=True, null=True)

    @staticmethod
    def update_status(chain, bright_user):
        # verified and rejected receipts don't get updated,
        # so only update pending receipts
        for pending_recept in ClaimReceipt.objects.filter(chain=chain,
                                                          bright_user=bright_user,
                                                          _status=ClaimReceipt.PENDING):
            # todo: fetch status from blockchain
            pass

    def get_status(self) -> states:
        if self._status in [self.VERIFIED, self.REJECTED]:
            return self._status
        self.update_status(self.chain, self.bright_user)
        return self._status
