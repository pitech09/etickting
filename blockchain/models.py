from django.db import models


class TicketOwnershipProof(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        FAILED = "failed", "Failed"

    ticket = models.OneToOneField("ticketing.Ticket", on_delete=models.PROTECT, related_name="blockchain_proof")
    network = models.CharField(max_length=40, default="polygon")
    token_reference = models.CharField(max_length=200, blank=True)
    transaction_hash = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
