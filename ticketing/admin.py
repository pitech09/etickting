from django.contrib import admin

from .models import Admission, Event, Ticket, TicketCredential, TicketOwnershipHistory, ScanAttempt, ScannerDevice, SigningKey

for model in (Event, Ticket, TicketCredential, TicketOwnershipHistory, ResaleListing, ScannerDevice, ScanAttempt, Admission, SigningKey):
    admin.site.register(model)
