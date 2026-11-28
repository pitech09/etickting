from django.urls import path

from .views import commission_settings, event_report, report, request_event_payout

app_name = "finance"
urlpatterns = [
    path("organisations/<uuid:organisation_id>/report/", report, name="report"),
    path("events/<uuid:event_id>/report/", event_report, name="event-report"),
    path("events/<uuid:event_id>/payouts/request/", request_event_payout, name="event-payout-request"),
    path("platform/commission/", commission_settings, name="commission-settings"),
]
