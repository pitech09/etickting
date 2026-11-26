from django.urls import path

from .views import (
    order_confirmation,
    order_create,
    order_cancel,
    order_detail,
    payment_status,
    order_list,
)

app_name = "orders"

urlpatterns = [
    path("", order_list, name="order-list"),
    path("<uuid:event_id>/create/", order_create, name="order-create"),
    path("<uuid:pk>/", order_detail, name="order-detail"),
    path("<uuid:pk>/payment-status/", payment_status, name="payment-status"),
    path("<uuid:pk>/confirm/", order_confirmation, name="order-confirmation"),
    path("<uuid:pk>/cancel/", order_cancel, name="order-cancel"),
]
