from django.urls import path

from .views import organisation_create, organisation_update, payment_method_create, payment_method_delete

app_name = "organisations"

urlpatterns = [
    path("create/", organisation_create, name="create"),
    path("<uuid:organisation_id>/edit/", organisation_update, name="edit"),
    path("<uuid:organisation_id>/payment-methods/add/", payment_method_create, name="payment-method-create"),
    path("<uuid:organisation_id>/payment-methods/<uuid:method_id>/delete/", payment_method_delete, name="payment-method-delete"),
]
