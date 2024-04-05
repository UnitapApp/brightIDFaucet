from rest_framework import filters
from rest_framework.generics import get_object_or_404

from core.models import Chain


class IsOwnerFilterBackend(filters.BaseFilterBackend):
    """
    Filter that only allows users to see their own objects.
    """

    def filter_queryset(self, request, queryset, view):
        return queryset.filter(user_profile=request.user.profile)


class ChainFilterBackend(filters.BaseFilterBackend):
    """
    Filter that filter nested faucet
    """

    def filter_queryset(self, request, queryset, view):
        chain_pk = request.query_params.get("chain_pk")
        if chain_pk is None:
            return queryset
        return queryset.filter(chain=get_object_or_404(Chain, pk=chain_pk))
