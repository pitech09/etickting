from django.contrib import admin

from .models import CommissionTransaction, FinancialTransaction, LedgerEntry, Payout, PlatformCommissionConfig, RefundCommissionAdjustment

admin.site.register((FinancialTransaction, LedgerEntry, Payout))
admin.site.register((PlatformCommissionConfig, CommissionTransaction, RefundCommissionAdjustment))
