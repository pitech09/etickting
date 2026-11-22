from django.contrib import admin

from .models import Admission, Event, OfflineScanBatch, OfflineScanRecord, Ticket, TicketCredential, TicketOwnershipHistory, ResaleListing, ScanAttempt, ScannerDevice, SigningKey

for model in (Event, Ticket, TicketCredential, TicketOwnershipHistory, ResaleListing, ScannerDevice, ScanAttempt, Admission, OfflineScanBatch, OfflineScanRecord, SigningKey):
    admin.site.register(model)
