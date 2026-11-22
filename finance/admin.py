from django.contrib import admin

from .models import FinancialTransaction, LedgerEntry, Payout

admin.site.register((FinancialTransaction, LedgerEntry, Payout))
