from django.contrib import admin
from .models import *

# Register your models here.


class TokenDistributionAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "name",
        "token",
        "token_address",
        "amount",
        "chain",
        "created_at",
        "deadline",
    ]


class TokenDistributionClaimAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "token_distribution",
        "user_profile",
        "created_at",
    ]


admin.site.register(TokenDistribution, TokenDistributionAdmin)
admin.site.register(TokenDistributionClaim, TokenDistributionClaimAdmin)