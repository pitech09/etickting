from django.contrib import admin

from .models import EventSeating, SeatingRow, SeatingSection, Seat, SeatAllocation, SeatReservation


@admin.register(SeatingSection)
class SeatingSectionAdmin(admin.ModelAdmin):
    list_display = ("name", "venue", "ticket_price_minor", "price_modifier_minor", "is_accessible", "sort_order")
    list_filter = ("venue", "is_accessible")
    search_fields = ("name", "venue__name")
    ordering = ("venue", "sort_order", "name")


@admin.register(SeatingRow)
class SeatingRowAdmin(admin.ModelAdmin):
    list_display = ("name", "section", "sort_order")
    list_filter = ("section__venue", "section")
    search_fields = ("name", "section__name")
    ordering = ("section", "sort_order", "name")


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("label", "row", "status", "is_accessible", "is_restricted_view")
    list_filter = ("status", "is_accessible", "is_restricted_view", "row__section__venue")
    search_fields = ("label", "number", "row__name")
    ordering = ("row__section", "row__sort_order", "sort_order", "number")


@admin.register(EventSeating)
class EventSeatingAdmin(admin.ModelAdmin):
    list_display = ("event", "venue", "is_active")
    list_filter = ("is_active", "venue")
    search_fields = ("event__name", "venue__name")


@admin.register(SeatReservation)
class SeatReservationAdmin(admin.ModelAdmin):
    list_display = ("seat", "event", "session_key", "status", "expires_at")
    list_filter = ("status", "event")
    search_fields = ("seat__label", "session_key", "event__name")
    ordering = ("-created_at",)


@admin.register(SeatAllocation)
class SeatAllocationAdmin(admin.ModelAdmin):
    list_display = ("seat", "ticket", "created_at")
    search_fields = ("seat__label", "ticket__reference")
    ordering = ("-created_at",)
