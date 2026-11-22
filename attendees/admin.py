from django.contrib import admin

from .models import AttendeeProfile


@admin.register(AttendeeProfile)
class AttendeeProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "phone_number", "updated_at")
