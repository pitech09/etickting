from django.contrib.contenttypes.models import ContentType

from .models import AuditLog


def record(*, action, actor=None, obj=None, metadata=None):
    content_type = ContentType.objects.get_for_model(obj) if obj else None
    return AuditLog.objects.create(actor=actor, action=action, object_type=content_type, object_id=str(obj.pk) if obj else "", metadata=metadata or {})
