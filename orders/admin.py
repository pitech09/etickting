from django.contrib import admin

from .models import Order, OrderLine


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "event",
        "customer",
        "status",
        "currency",
        "total_minor",
        "is_paid",
    )
    list_filter = ("status", "currency", "event__status")
    search_fields = ("reference", "customer__email", "event__name")
    raw_id_fields = ("customer", "event")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"


@admin.register(OrderLine)
class OrderLineAdmin(admin.ModelAdmin):
    list_display = ("order", "line_type", "display_label", "quantity", "unit_price_minor", "line_total_minor")
    list_filter = ("line_type",)
    search_fields = ("order__reference", "seat__label", "ticket_category__name")
    raw_id_fields = ("order", "seat", "ticket_category")
    ordering = ("order",)

    @admin.display(description="Item")
    def display_label(self, obj):
        if obj.line_type == OrderLine.LineType.TICKET_CATEGORY:
            return f"{obj.ticket_category.name} x{obj.quantity}"
        return f"Seat {obj.seat.label}"