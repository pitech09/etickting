from django.http import JsonResponse
from django.conf import settings
from django.db import connection
from django.core.cache import cache


def health(request):
    return JsonResponse({"status": "ok", "service": "etickting"})


def readiness(request):
    checks = {"database": False, "redis": False}
    try:
        connection.ensure_connection()
        checks["database"] = True
    except Exception:
        pass
    try:
        cache.set("readiness-check", "ok", 5)
        checks["redis"] = cache.get("readiness-check") == "ok"
    except Exception:
        pass
    ready = all(checks.values()) if not settings.DEBUG else checks["database"]
    return JsonResponse({"status": "ready" if ready else "not_ready", "checks": checks, "redis_required": not settings.DEBUG}, status=200 if ready else 503)
