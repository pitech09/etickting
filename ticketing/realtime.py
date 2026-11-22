from asgiref.sync import async_to_sync
from django.db import transaction

try:
    from channels.layers import get_channel_layer
except ImportError:  # Optional during local tests; Redis/WebSockets remain deployment features.
    get_channel_layer = None


def publish_inventory_update(event_id, changed_seat_ids=None):
    """Publish only after commit; Redis/WebSocket outages must not break sales."""
    def publish():
        try:
            layer = get_channel_layer() if get_channel_layer else None
            if layer is None:
                return
            async_to_sync(layer.group_send)(
                f"event-inventory-{event_id}",
                {"type": "inventory.update", "event_id": str(event_id), "changed_seat_ids": [str(value) for value in (changed_seat_ids or [])]},
            )
        except Exception:
            return
    transaction.on_commit(publish)
