from django.contrib import admin

from .models import Payment, PaymentReview, RefundRequest


admin.site.register((Payment, PaymentReview, RefundRequest))
