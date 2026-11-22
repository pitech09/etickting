from django.contrib import admin

from .models import Venue


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "country", "capacity", "organisation", "created_at")
    list_filter = ("country", "organisation")
    search_fields = ("name", "city", "slug")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("organisation",)