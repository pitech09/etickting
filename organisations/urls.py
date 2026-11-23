from django.urls import path

from .views import (
    device_create,
    device_deactivate,
    member_add,
    member_remove,
    member_update,
    organisation_create,
    organisation_update,
    payment_method_create,
    payment_method_delete,
)

app_name = "organisations"

urlpatterns = [
    path("create/", organisation_create, name="create"),
    path("<uuid:organisation_id>/edit/", organisation_update, name="edit"),
    path("<uuid:organisation_id>/payment-methods/add/", payment_method_create, name="payment-method-create"),
    path("<uuid:organisation_id>/payment-methods/<uuid:method_id>/delete/", payment_method_delete, name="payment-method-delete"),
    path("<uuid:organisation_id>/members/add/", member_add, name="member-add"),
    path("<uuid:organisation_id>/members/<int:membership_id>/role/", member_update, name="member-update"),
    path("<uuid:organisation_id>/members/<int:membership_id>/remove/", member_remove, name="member-remove"),
    path("<uuid:organisation_id>/scanner-devices/add/", device_create, name="device-create"),
    path("<uuid:organisation_id>/scanner-devices/<int:device_id>/deactivate/", device_deactivate, name="device-deactivate"),
]
