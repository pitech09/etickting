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
    InventoryDashboardView,
    inventory_data,
    public_verify,
    public_verify_page,
    scan,
    scanner_page,
)
from .wallet import ticket_detail, ticket_qr, update_attendee, wallet
from .offline import reconcile_offline_scans, upload_offline_scans
from .marketplace import listing_create, listing_list, listing_purchase

app_name = "ticketing"

urlpatterns = [
    path("<uuid:pk>/inventory/", InventoryDashboardView.as_view(), name="inventory-dashboard"),
    path("<uuid:event_id>/inventory/data/", inventory_data, name="inventory-data"),
    path("wallet/", wallet, name="ticket-wallet"),
    path("wallet/<uuid:pk>/", ticket_detail, name="ticket-detail"),
    path("wallet/<uuid:pk>/attendee/", update_attendee, name="ticket-attendee-update"),
    path("wallet/<uuid:pk>/qr.png", ticket_qr, name="ticket-qr"),
    path("marketplace/", listing_list, name="marketplace"),
    path("wallet/<uuid:ticket_id>/resell/", listing_create, name="marketplace-list"),
    path("marketplace/<int:listing_id>/purchase/", listing_purchase, name="marketplace-purchase"),
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
    path("events/<uuid:event_id>/scan/offline/", upload_offline_scans, name="ticket-offline-upload"),
    path("scan/offline/<uuid:batch_id>/reconcile/", reconcile_offline_scans, name="ticket-offline-reconcile"),
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
        "categories/<int:pk>/edit/",
        TicketCategoryUpdateView.as_view(),
        name="ticket-category-update",
    ),
    path(
        "categories/<int:pk>/delete/",
        TicketCategoryDeleteView.as_view(),
        name="ticket-category-delete",
    ),
]
