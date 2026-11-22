from django.urls import path

from .views import VenueDetailView, VenueListView, VenueUpdateView

urlpatterns = [
    path("", VenueListView.as_view(), name="venue-list"),
    path("<uuid:pk>/", VenueDetailView.as_view(), name="venue-detail"),
    path("<uuid:pk>/edit/", VenueUpdateView.as_view(), name="venue-update"),
]
