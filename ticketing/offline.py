import json
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db import transaction

from .models import Event, OfflineScanBatch, OfflineScanRecord, ScannerDevice
from .services import verify_credential
from .services import admit_ticket


@login_required
@require_POST
def upload_offline_scans(request, event_id):
    event = get_object_or_404(Event, pk=event_id, organisation__memberships__user=request.user)
    device_id = request.headers.get("X-Scanner-Device", "")
    device = get_object_or_404(ScannerDevice, event=event, user=request.user, device_id=device_id, active=True)
    try:
        records = json.loads(request.body).get("records", [])
    except (TypeError, ValueError):
        return JsonResponse({"detail": "Invalid offline scan payload"}, status=400)
    if len(records) > 500:
        return JsonResponse({"detail": "Offline batch is too large"}, status=400)
    batch = OfflineScanBatch.objects.create(event=event, device=device, uploaded_by=request.user)
    accepted = 0
    for item in records:
        credential = str(item.get("credential", ""))
        _, result = verify_credential(credential, expected_event=event)
        try:
            scanned_at = datetime.fromisoformat(item.get("scanned_at", "")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            scanned_at = timezone.now()
        OfflineScanRecord.objects.create(batch=batch, credential=credential, signature_valid=result not in {"invalid", "wrong_event"}, result=f"pending:{result}", scanned_at=scanned_at)
        accepted += 1
    return JsonResponse({"batch_id": str(batch.id), "accepted": accepted, "status": batch.status})


@login_required
@require_POST
def reconcile_offline_scans(request, batch_id):
    with transaction.atomic():
        batch = get_object_or_404(OfflineScanBatch.objects.select_for_update().select_related("event", "device"), pk=batch_id, uploaded_by=request.user)
        if batch.status == OfflineScanBatch.Status.RECONCILED:
            return JsonResponse({"batch_id": str(batch.id), "status": batch.status, "replayed": True})
        processed = 0
        for record in batch.records.select_for_update().all():
            ticket, result = admit_ticket(credential=record.credential, event=batch.event, user=request.user, device_id=batch.device.device_id)
            record.result = f"reconciled:{result}"
            record.save(update_fields=["result"])
            processed += 1
        batch.status = OfflineScanBatch.Status.RECONCILED
        batch.reconciled_at = timezone.now()
        batch.save(update_fields=["status", "reconciled_at"])
    return JsonResponse({"batch_id": str(batch.id), "status": batch.status, "processed": processed})
