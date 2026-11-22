from django.urls import path

from .views import (
    order_confirmation,
    order_create,
    order_detail,
    order_list,
)

app_name = "orders"

urlpatterns = [
    path("", order_list, name="order-list"),
    path("create/", order_create, name="order-create"),
    path("<uuid:pk>/", order_detail, name="order-detail"),
    path("<uuid:pk>/confirm/", order_confirmation, name="order-confirmation"),
]