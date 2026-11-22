from django.urls import path

from .views import (
    EventCreateView,
    EventDetailView,
    EventListView,
    EventPublishView,
    EventSalesOpenView,
    EventUpdateView,
    TicketCategoryCreateView,
    TicketCategoryDeleteView,
    TicketCategoryListView,
    TicketCategoryUpdateView,
    public_verify,
    public_verify_page,
    scan,
    scanner_page,
)

app_name = "ticketing"

urlpatterns = [
    path("", EventListView.as_view(), name="event-list"),
    path("create/", EventCreateView.as_view(), name="event-create"),
    path("<uuid:pk>/", EventDetailView.as_view(), name="event-detail"),
    path("<uuid:pk>/edit/", EventUpdateView.as_view(), name="event-update"),
    path("<uuid:pk>/publish/", EventPublishView.as_view(), name="event-publish"),
    path("<uuid:pk>/sales-open/", EventSalesOpenView.as_view(), name="event-sales-open"),
    path("verify/page/", public_verify_page, name="ticket-public-verify-page"),
    path("verify/", public_verify, name="ticket-public-verify"),
    path("events/<uuid:event_id>/scan/console/", scanner_page, name="ticket-scanner-page"),
    path("events/<uuid:event_id>/scan/", scan, name="ticket-scan"),
    path(
        "events/<uuid:event_id>/categories/",
        TicketCategoryListView.as_view(),
        name="ticket-category-list",
    ),
    path(
        "events/<uuid:event_id>/categories/create/",
        TicketCategoryCreateView.as_view(),
        name="ticket-category-create",
    ),
    path(
        "categories/<uuid:pk>/edit/",
        TicketCategoryUpdateView.as_view(),
        name="ticket-category-update",
    ),
    path(
        "categories/<uuid:pk>/delete/",
        TicketCategoryDeleteView.as_view(),
        name="ticket-category-delete",
    ),
]
