import base64
import binascii
import hashlib
import json
import secrets

from cryptography.exceptions import InvalidSignature
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from organisations.models import OrganisationMembership

from .key_management import decrypt_credential, encrypt_credential, signing_keys, verification_keys
from .models import Admission, ResaleListing, ScanAttempt, ScannerDevice, Ticket, TicketCredential, TicketOwnershipHistory


def _b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _payload(ticket, nonce):
    return {"v": 1, "jti": str(ticket.id), "event": str(ticket.event_id), "reference": ticket.reference, "nonce": nonce}


def _credential(ticket, key_id, private_key):
    payload = _b64(json.dumps(_payload(ticket, secrets.token_urlsafe(18)), separators=(",", ":"), sort_keys=True).encode())
    signature = _b64(private_key.sign(payload.encode()))
    return f"{key_id}.{payload}.{signature}"


def _credential_hash(credential):
    return hashlib.sha256(credential.encode()).hexdigest()


def issue_ticket(*, event, owner, payment_verified=False, complimentary_authorized=False, attendee_name="", seat_label="", ticket_category=None, seat=None):
    keys = signing_keys()
    if not keys:
        raise ValidationError("Ticket signing is not configured")
    if not (payment_verified or complimentary_authorized):
        raise ValidationError("A ticket requires verified payment or authorised complimentary issuance")
    key_id, private_key = next(iter(keys.items()))
    with transaction.atomic():
        ticket = Ticket.objects.create(
            event=event, owner=owner, reference=secrets.token_urlsafe(12), attendee_name=attendee_name,
            seat_label=seat_label or (seat.label if seat else ""), seat=seat, ticket_category=ticket_category,
            payment_verified_at=timezone.now() if payment_verified else None,
            complimentary_authorized_at=timezone.now() if complimentary_authorized else None,
        )
        credential = _credential(ticket, key_id, private_key)
        ticket.credential_hash = _credential_hash(credential)
        ticket.key_id = key_id
        ticket.save(update_fields=["credential_hash", "key_id", "updated_at"])
        TicketCredential.objects.create(ticket=ticket, credential_hash=_credential_hash(credential), key_id=key_id, encrypted_credential=encrypt_credential(credential))
        from .realtime import publish_inventory_update
        publish_inventory_update(event.id, [ticket.seat_id] if ticket.seat_id else None)
    from notifications.services import deliver_ticket
    deliver_ticket(ticket=ticket)
    return ticket, credential


def verify_credential(credential, *, expected_event=None):
    try:
        key_id, encoded_payload, encoded_signature = credential.split(".", 2)
        public_key = verification_keys()[key_id]
        public_key.verify(_unb64(encoded_signature), encoded_payload.encode())
        payload = json.loads(_unb64(encoded_payload))
        if payload.get("v") != 1 or not payload.get("jti") or not payload.get("event") or not payload.get("nonce"):
            raise ValueError
    except (KeyError, ValueError, InvalidSignature, TypeError, binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        return None, "invalid"
    credential_record = TicketCredential.objects.select_related("ticket", "ticket__event", "ticket__owner").filter(credential_hash=_credential_hash(credential)).first()
    if not credential_record or str(credential_record.ticket_id) != payload["jti"] or str(credential_record.ticket.event_id) != payload["event"] or credential_record.ticket.reference != payload.get("reference"):
        return None, "invalid"
    ticket = credential_record.ticket
    if expected_event and ticket.event_id != expected_event.id:
        return None, "wrong_event"
    if credential_record.state != TicketCredential.State.CURRENT:
        return ticket, "transferred" if credential_record.state == TicketCredential.State.TRANSFERRED else "revoked"
    if ticket.status in {Ticket.Status.CANCELLED, Ticket.Status.REFUNDED, Ticket.Status.REVOKED}:
        return ticket, ticket.status
    return ticket, "valid"


def _staff_device(user, event, device_id):
    if not device_id:
        return None
    allowed_roles = {OrganisationMembership.Role.OWNER, OrganisationMembership.Role.EVENT_MANAGER, OrganisationMembership.Role.EVENT_STAFF}
    if not OrganisationMembership.objects.filter(organisation=event.organisation, user=user, role__in=allowed_roles).exists():
        return None
    return ScannerDevice.objects.filter(device_id=device_id, event=event, user=user, active=True).first()


@transaction.atomic
def admit_ticket(*, credential, event, user, device_id):
    device = _staff_device(user, event, device_id)
    if not device:
        ScanAttempt.objects.create(event=event, scanner=user, result=ScanAttempt.Result.UNAUTHORISED, reason="invalid scanner or event access")
        return None, "unauthorised"
    ticket, result = verify_credential(credential, expected_event=event)
    if not ticket:
        ScanAttempt.objects.create(event=event, scanner=user, device=device, result=ScanAttempt.Result.INVALID, reason=result)
        return None, result
    ticket = Ticket.objects.select_for_update().select_related("owner").get(pk=ticket.pk)
    if result != "valid":
        ScanAttempt.objects.create(ticket=ticket, event=event, scanner=user, device=device, result=ScanAttempt.Result.INVALID, reason=result)
        return ticket, result
    if hasattr(ticket, "admission"):
        if event.admission_policy == "reentry":
            admission = ticket.admission
            admission.reentry_count += 1
            admission.save(update_fields=["reentry_count"])
            ScanAttempt.objects.create(ticket=ticket, event=event, scanner=user, device=device, result=ScanAttempt.Result.VALID, reason="reentry")
            return ticket, "reentry"
        ScanAttempt.objects.create(ticket=ticket, event=event, scanner=user, device=device, result=ScanAttempt.Result.USED, reason="already admitted")
        return ticket, "used"
    Admission.objects.create(ticket=ticket, event=event, admitted_by=user)
    ticket.status = Ticket.Status.ADMITTED
    ticket.save(update_fields=["status", "updated_at"])
    ScanAttempt.objects.create(ticket=ticket, event=event, scanner=user, device=device, result=ScanAttempt.Result.VALID)
    from .realtime import publish_inventory_update
    publish_inventory_update(event.id, [ticket.seat_id] if ticket.seat_id else None)
    return ticket, "valid"


@transaction.atomic
def transfer_ticket(*, ticket_id, current_owner, new_owner):
    ticket = Ticket.objects.select_for_update().select_related("event").get(pk=ticket_id)
    if ticket.owner_id != current_owner.id:
        raise PermissionDenied("Only the current owner can transfer this ticket")
    if ticket.status != Ticket.Status.ISSUED:
        raise ValidationError("Only an issued ticket can be transferred")
    keys = signing_keys()
    if not keys:
        raise ValidationError("Ticket signing is not configured")
    old = ticket.credentials.filter(state=TicketCredential.State.CURRENT).first()
    if old:
        old.state = TicketCredential.State.TRANSFERRED
        old.revoked_at = timezone.now()
        old.save(update_fields=["state", "revoked_at"])
    ticket.owner = new_owner
    ticket.save(update_fields=["owner", "updated_at"])
    TicketOwnershipHistory.objects.create(ticket=ticket, previous_owner=current_owner, new_owner=new_owner)
    key_id, private_key = next(iter(keys.items()))
    credential = _credential(ticket, key_id, private_key)
    ticket.credential_hash = _credential_hash(credential)
    ticket.key_id = key_id
    ticket.save(update_fields=["credential_hash", "key_id", "updated_at"])
    TicketCredential.objects.create(ticket=ticket, credential_hash=_credential_hash(credential), key_id=key_id, encrypted_credential=encrypt_credential(credential))
    return ticket, credential


def current_credential(ticket):
    record = ticket.credentials.filter(state=TicketCredential.State.CURRENT).first()
    if not record or not record.encrypted_credential:
        return None
    return decrypt_credential(record.encrypted_credential)


@transaction.atomic
def create_resale_listing(*, ticket_id, seller, price_minor):
    ticket = Ticket.objects.select_for_update().get(pk=ticket_id)
    if ticket.owner_id != seller.id or ticket.status != Ticket.Status.ISSUED:
        raise PermissionDenied("Only the current holder of an issued ticket can list it")
    if price_minor < 0:
        raise ValidationError("Price cannot be negative")
    return ResaleListing.objects.create(ticket=ticket, seller=seller, price_minor=price_minor)


@transaction.atomic
def purchase_resale(*, listing_id, buyer, payment_verified):
    listing = ResaleListing.objects.select_for_update().select_related("ticket", "seller").get(pk=listing_id)
    if listing.status != ResaleListing.Status.OPEN:
        raise ValidationError("This resale listing is no longer available")
    if not payment_verified:
        raise ValidationError("Resale payment must be verified before ownership changes")
    ticket, credential = transfer_ticket(ticket_id=listing.ticket_id, current_owner=listing.seller, new_owner=buyer)
    listing.buyer = buyer
    listing.status = ResaleListing.Status.SOLD
    listing.payment_verified_at = timezone.now()
    listing.save(update_fields=["buyer", "status", "payment_verified_at", "updated_at"])
    return ticket, credential
