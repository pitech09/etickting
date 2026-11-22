from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class InventoryConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.event_id = self.scope["url_route"]["kwargs"]["event_id"]
        if not self.scope["user"].is_authenticated or not await self.has_access():
            await self.close(code=4403)
            return
        self.group_name = f"event-inventory-{self.event_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def inventory_update(self, event):
        await self.send_json({"type": "inventory.update", "event_id": event["event_id"], "changed_seat_ids": event.get("changed_seat_ids", [])})

    @database_sync_to_async
    def has_access(self):
        from organisations.models import OrganisationMembership
        from ticketing.models import Event
        return OrganisationMembership.objects.filter(organisation__events__id=self.event_id, user=self.scope["user"]).exists()
