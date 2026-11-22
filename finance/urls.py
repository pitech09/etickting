from django.urls import path

from .views import report

app_name = "finance"
urlpatterns = [path("organisations/<uuid:organisation_id>/report/", report, name="report")]
