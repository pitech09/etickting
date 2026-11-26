from django.urls import path

from .views import customer_dashboard, dashboard, event_attendee_export, payment_proof, pending_payments, platform_dashboard, platform_event_action, platform_user_toggle, public_event_detail, public_event_list, public_home, review_payment

urlpatterns = [
    path("", public_home, name="home"),
    path("events/", public_event_list, name="public-event-list"),
    path("events/<uuid:pk>/", public_event_detail, name="public-event-detail"),
    path("dashboard/", dashboard, name="dashboard"),
    path("platform/", platform_dashboard, name="platform-dashboard"),
    path("platform/users/<int:user_id>/toggle/", platform_user_toggle, name="platform-user-toggle"),
    path("platform/events/<uuid:event_id>/action/", platform_event_action, name="platform-event-action"),
    path("dashboard/pending-payments/", pending_payments, name="pending-payments"),
    path("dashboard/pending-payments/<uuid:payment_id>/review/", review_payment, name="review-payment"),
    path("dashboard/pending-payments/<uuid:payment_id>/proof/", payment_proof, name="payment-proof"),
    path("dashboard/events/<uuid:event_id>/attendees.csv", event_attendee_export, name="event-attendee-export"),
    path("account/", customer_dashboard, name="customer-dashboard"),
]
