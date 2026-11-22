from django.urls import path

from .views import customer_dashboard, dashboard, payment_proof, pending_payments, public_event_detail, public_event_list, public_home, review_payment

urlpatterns = [
    path("", public_home, name="home"),
    path("events/", public_event_list, name="public-event-list"),
    path("events/<uuid:pk>/", public_event_detail, name="public-event-detail"),
    path("dashboard/", dashboard, name="dashboard"),
    path("dashboard/pending-payments/", pending_payments, name="pending-payments"),
    path("dashboard/pending-payments/<uuid:payment_id>/review/", review_payment, name="review-payment"),
    path("dashboard/pending-payments/<uuid:payment_id>/proof/", payment_proof, name="payment-proof"),
    path("account/", customer_dashboard, name="customer-dashboard"),
]
