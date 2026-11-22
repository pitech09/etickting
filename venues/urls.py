from django.urls import path

from .views import VenueCreateView, VenueDetailView, VenueListView, VenueUpdateView

urlpatterns = [
    path("", VenueListView.as_view(), name="venue-list"),
    path("create/", VenueCreateView.as_view(), name="venue-create"),
    path("<uuid:pk>/", VenueDetailView.as_view(), name="venue-detail"),
    path("<uuid:pk>/edit/", VenueUpdateView.as_view(), name="venue-update"),
]