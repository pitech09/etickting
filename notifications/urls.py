from django.urls import path

from .views import inbox, mark_all_read, mark_read

app_name = "notifications"
urlpatterns = [
    path("", inbox, name="inbox"),
    path("read-all/", mark_all_read, name="mark-all-read"),
    path("<int:pk>/read/", mark_read, name="mark-read"),
]
