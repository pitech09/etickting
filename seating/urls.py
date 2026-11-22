from django.urls import path

from .views import (
    event_seating_map,
    event_seat_map,
    generate_seats,
    reserve_customer_seats,
    seat_list,
    SeatingRowCreateView,
    SeatingRowListView,
    SeatingSectionCreateView,
    SeatingSectionListView,
    SeatUpdateView,
)

app_name = "seating"

urlpatterns = [
    # Venue sections
    path(
        "venues/<uuid:venue_id>/sections/",
        SeatingSectionListView.as_view(),
        name="section-list",
    ),
    path(
        "venues/<uuid:venue_id>/sections/create/",
        SeatingSectionCreateView.as_view(),
        name="section-create",
    ),
    # Section rows
    path(
        "sections/<uuid:section_id>/rows/",
        SeatingRowListView.as_view(),
        name="row-list",
    ),
    path(
        "sections/<uuid:section_id>/rows/create/",
        SeatingRowCreateView.as_view(),
        name="row-create",
    ),
    # Row seats
    path(
        "rows/<uuid:row_id>/seats/",
        seat_list,
        name="seat-list",
    ),
    path(
        "rows/<uuid:row_id>/seats/generate/",
        generate_seats,
        name="seat-generate",
    ),
    path(
        "seats/<uuid:pk>/edit/",
        SeatUpdateView.as_view(),
        name="seat-update",
    ),
    # Customer seating map
    path(
        "events/<uuid:event_id>/map/",
        event_seating_map,
        name="event-map",
    ),
    path(
        "events/<uuid:event_id>/seat-map/",
        event_seat_map,
        name="event-seat-map",
    ),
    path(
        "events/<uuid:event_id>/reserve-seats/",
        reserve_customer_seats,
        name="reserve-seats",
    ),
]