from .models import Notification
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse


def notify(*, user, title, message, action_url=""):
    if action_url and not action_url.startswith("/"):
        raise ValueError("Notification action links must be internal paths")
    return Notification.objects.create(user=user, title=title, message=message, action_url=action_url)


def deliver_ticket(*, ticket):
    """Deliver an issued ticket through configured channels."""
    message = (
        f"Your ticket for {ticket.event.name} is ready.\n\n"
        f"Reference: {ticket.reference}\n"
        f"Date: {ticket.event.starts_at:%d %B %Y, %H:%M}\n"
        "Open eTickting to view your secure QR ticket."
    )
    email_sent = False
    if ticket.owner.email:
        email_sent = bool(send_mail(
            subject=f"Your eTickting ticket for {ticket.event.name}",
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "tickets@etickting.local"),
            recipient_list=[ticket.owner.email],
            fail_silently=True,
        ))
    notification = notify(
        user=ticket.owner,
        title="Ticket issued",
        message=message,
        action_url=reverse("ticketing:ticket-detail", args=[ticket.pk]),
    )
    return {"email_sent": email_sent, "sms_sent": False, "notification_id": notification.id}
