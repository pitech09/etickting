import logging

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import ContactForm

logger = logging.getLogger(__name__)


SERVICE_WORKER = """const CACHE_NAME = \"kena-shell-v1\";
const APP_SHELL = [\"/\", \"/static/manifest.webmanifest\", \"/static/icons/kena-192.png\", \"/static/icons/kena-512.png\"];

self.addEventListener(\"install\", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener(\"activate\", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener(\"fetch\", (event) => {
  if (event.request.method !== \"GET\") return;
  const requestUrl = new URL(event.request.url);
  if (requestUrl.origin !== self.location.origin) return;

  if (requestUrl.pathname.startsWith(\"/static/\")) {
    event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request).then((response) => {
      const copy = response.clone();
      caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
      return response;
    })));
    return;
  }

  if (event.request.mode === \"navigate\") {
    event.respondWith(fetch(event.request).catch(() => caches.match(\"/\")));
  }
});
"""


def health(request):
    return JsonResponse({"status": "ok", "service": "kena"})


def service_worker(request):
    return HttpResponse(
        SERVICE_WORKER,
        content_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


def readiness(request):
    checks = {"database": False, "redis": False}
    try:
        connection.ensure_connection()
        checks["database"] = True
    except Exception:
        pass
    if settings.REDIS_CONFIGURED:
        try:
            cache.set("readiness-check", "ok", 5)
            checks["redis"] = cache.get("readiness-check") == "ok"
        except Exception:
            pass
    ready = all(checks.values()) if not settings.DEBUG else checks["database"]
    return JsonResponse({"status": "ready" if ready else "not_ready", "checks": checks, "redis_required": not settings.DEBUG}, status=200 if ready else 503)


@require_http_methods(["GET", "POST"])
def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            EmailMessage(
                subject=f"Kena contact: {form.cleaned_data['subject']}",
                body=(
                    f"Name: {form.cleaned_data['name']}\n"
                    f"Email: {form.cleaned_data['email']}\n\n"
                    f"{form.cleaned_data['message']}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.SUPPORT_EMAIL],
                reply_to=[form.cleaned_data["email"]],
            ).send(fail_silently=False)
        except Exception:
            logger.exception("Kena contact form delivery failed")
            messages.error(request, "We could not send your message right now. Please email or WhatsApp Kena support directly.")
        else:
            messages.success(request, "Thanks. Your message has been sent to Kena support.")
            return redirect("contact")
    return render(request, "core/contact.html", {"form": form})


def customer_terms(request):
    return render(request, "core/customer_terms.html")


def organiser_terms(request):
    return render(request, "core/organiser_terms.html")
