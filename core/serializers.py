from rest_framework import serializers

from core.constraints import ConstraintVerification, get_constraint

from .models import Chain, UserConstraint


class ChainSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chain
        fields = [
            "pk",
            "chain_name",
            "chain_id",
            "native_currency_name",
            "symbol",
            "decimals",
            "explorer_url",
            "rpc_url",
            "logo_url",
            "modal_url",
            "is_testnet",
            "chain_type",
        ]


class UserConstraintBaseSerializer(serializers.Serializer):
    pk = serializers.IntegerField()
    name = serializers.CharField()
    title = serializers.CharField()
    type = serializers.ChoiceField(choices=UserConstraint.Type.choices)
    description = serializers.CharField()
    explanation = serializers.CharField()
    response = serializers.CharField()
    icon_url = serializers.CharField()
    params = serializers.SerializerMethodField()

    class Meta:
        fields = [
            "pk",
            "name",
            "title",
            "type",
            "description",
            "negative_description",
            "explanation",
            "response",
            "icon_url",
            "params",
        ]
        read_only_fields = [
            "pk",
            "name",
            "title",
            "type",
            "description",
            "negative_description",
            "explanation",
            "response",
            "icon_url",
            "params",
        ]

    def get_params(self, constraint: UserConstraint):
        c_class: ConstraintVerification = get_constraint(constraint.name)
        return [p.name for p in c_class.param_keys()]
