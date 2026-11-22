from django.contrib import admin
from django.urls import include, path

from core.views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("accounts/", include("accounts.urls")),
    path("tickets/", include("ticketing.urls")),
    path("venues/", include("venues.urls")),
    path("seating/", include("seating.urls")),
    path("", include("dashboard.urls")),
]
