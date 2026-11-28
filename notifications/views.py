from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def inbox(request):
    notifications = Notification.objects.filter(user=request.user)
    return render(request, "notifications/inbox.html", {
        "notifications": notifications,
        "unread_count": notifications.filter(read_at__isnull=True).count(),
    })


@login_required
@require_POST
def mark_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
        messages.success(request, "Notification marked as read.")
    return redirect(notification.action_url or "notifications:inbox")


@login_required
@require_POST
def mark_all_read(request):
    updated = Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())
    messages.success(request, f"{updated} notification(s) marked as read.")
    return redirect("notifications:inbox")
