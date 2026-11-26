from django.urls import path

from .views import commission_settings, report

app_name = "finance"
urlpatterns = [
    path("organisations/<uuid:organisation_id>/report/", report, name="report"),
    path("platform/commission/", commission_settings, name="commission-settings"),
]
