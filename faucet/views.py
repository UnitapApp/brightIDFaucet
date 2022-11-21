import rest_framework.exceptions
from django.http import Http404
from rest_framework.generics import CreateAPIView, RetrieveAPIView, ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from faucet.faucet_manager.claim_manager import ClaimManagerFactory
from faucet.models import BrightUser, Chain, ClaimReceipt, GlobalSettings
from faucet.serializers import (
    GlobalSettingsSerializer,
    ReceiptSerializer,
    UserSerializer,
    ChainSerializer,
    ChainFundSerializer
)


class CreateUserView(CreateAPIView):
    """
    Create an unverified user with the given address

    this user can be verified using verification_link
    """

    serializer_class = UserSerializer


class LastClaimView(RetrieveAPIView):
    serializer_class = ReceiptSerializer

    def get_object(self):
        try:
            return (
                ClaimReceipt.objects.filter(
                    bright_user__address=self.kwargs.get("address")
                )
                .order_by("pk")
                .last()
            )
        except ClaimReceipt.DoesNotExist:
            raise Http404(
                f"Claim Receipt with address {self.kwargs.get('address')} does not exist"
            )


class ListClaims(ListAPIView):
    serializer_class = ReceiptSerializer

    filterset_fields = {
        "chain": {"exact"},
        "_status": {"exact"},
        "datetime": {"exact", "gte", "lte"},
    }

    def get_queryset(self):
        return ClaimReceipt.objects.filter(
            bright_user__address=self.kwargs.get("address")
        ).order_by("-pk")


class UserInfoView(RetrieveAPIView):
    """
    User info of the given address
    """

    serializer_class = UserSerializer
    queryset = BrightUser.objects.all()

    lookup_field = "address"
    lookup_url_kwarg = "address"


class GetVerificationUrlView(RetrieveAPIView):
    """
    Return the bright verification url
    """

    serializer_class = UserSerializer

    def get_object(self):
        address = self.kwargs.get("address")
        try:
            return BrightUser.objects.get(address=address)
        except BrightUser.DoesNotExist:
            if address is not None:
                return BrightUser.objects.get_or_create(address)

            raise Http404


class ChainListView(ListAPIView):
    """
    list of supported chains

    this endpoint returns detailed user specific info if supplied with an address
    """

    serializer_class = ChainSerializer
    queryset = Chain.objects.all().order_by("order")


class GlobalSettingsView(RetrieveAPIView):
    serializer_class = GlobalSettingsSerializer

    def get_object(self):
        return GlobalSettings.objects.first()


class ClaimMaxView(APIView):
    """
    Claims maximum possible fee for the given user and chain

    **user must be verified**
    """

    def get_user(self) -> BrightUser:
        address = self.kwargs.get("address", None)
        try:
            return BrightUser.objects.get(address=address)
        except BrightUser.DoesNotExist:
            raise Http404(f"Bright User With Address {address} Does not Exist")

    def check_user_is_verified(self):
        _is_verified = self.get_user().verification_status == BrightUser.VERIFIED
        if not _is_verified:
            raise rest_framework.exceptions.NotAcceptable

    def get_chain(self) -> Chain:
        chain_pk = self.kwargs.get("chain_pk", None)
        try:
            return Chain.objects.get(pk=chain_pk)
        except Chain.DoesNotExist:
            raise Http404(f"Chain with id {chain_pk} Does not Exist")

    def get_claim_manager(self):
        return ClaimManagerFactory(self.get_chain(), self.get_user()).get_manager()

    def claim_max(self) -> ClaimReceipt:
        manager = self.get_claim_manager()
        max_credit = manager.get_credit_strategy().get_unclaimed()
        try:
            assert max_credit > 0
            return manager.claim(max_credit)
        except AssertionError as e:
            raise rest_framework.exceptions.PermissionDenied
        except ValueError as e:
            raise rest_framework.exceptions.APIException(e)

    def post(self, request, *args, **kwargs):
        self.check_user_is_verified()
        receipt = self.claim_max()
        return Response(ReceiptSerializer(instance=receipt).data)


class ChainFund(APIView):
    def get_object(self, chain_pk):
        try:
            return Chain.objects.get(pk=chain_pk)
        except Chain.DoesNotExist:
            raise Http404()

    def get(self, request, chain_pk):
        from web3 import Web3
        chain = self.get_object(chain_pk)
        eth_exponent = 10 ** 8
        RPC = Web3(Web3.HTTPProvider(chain.rpc_url))
        wallet_fund = RPC.eth.get_balance(chain.fund_manager_address) / eth_exponent
        data = ChainFundSerializer(data={
            'pk': chain.pk,
            'chainId': chain.chain_id,
            'fund': wallet_fund,
            'is_empty': wallet_fund == 0.0
        })
        data.is_valid(True)
        return Response(data.validated_data)


def error500(request):
    1 / 0
