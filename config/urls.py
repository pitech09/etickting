from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from core.views import health, readiness

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("health/ready/", readiness, name="readiness"),
    path("accounts/", include("accounts.urls")),
    path("organisations/", include("organisations.urls")),
    path("tickets/", include("ticketing.urls")),
    path("venues/", include("venues.urls")),
    path("seating/", include("seating.urls")),
    path("attendees/", include("attendees.urls")),
    path("finance/", include("finance.urls")),
    path("notifications/", include("notifications.urls")),
    path("orders/", include("orders.urls")),
    path("", include("dashboard.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
