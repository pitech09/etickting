from django.urls import re_path

from .consumers import InventoryConsumer

websocket_urlpatterns = [re_path(r"^ws/events/(?P<event_id>[0-9a-f-]+)/inventory/$", InventoryConsumer.as_asgi())]
