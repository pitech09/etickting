import io
import textwrap

import qrcode
from PIL import Image, ImageDraw, ImageFont
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from .forms import TicketAttendeeForm
from .models import Ticket
from .services import current_credential


@login_required
@require_GET
def wallet(request):
    tickets = Ticket.objects.filter(owner=request.user).select_related("event", "ticket_category", "seat").order_by("-issued_at")
    return render(request, "ticketing/wallet.html", {"tickets": tickets})


@login_required
@require_GET
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket.objects.select_related("event", "ticket_category", "seat"), pk=pk, owner=request.user)
    return render(request, "ticketing/ticket_detail.html", {"ticket": ticket, "form": TicketAttendeeForm(instance=ticket)})


@login_required
@require_POST
def update_attendee(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, owner=request.user)
    form = TicketAttendeeForm(request.POST, request.FILES, instance=ticket)
    if form.is_valid():
        form.save()
    return render(request, "ticketing/ticket_detail.html", {"ticket": ticket, "form": form})


@login_required
@require_GET
def ticket_qr(request, pk):
    ticket = get_object_or_404(
        Ticket.objects.select_related("event", "ticket_category", "seat"),
        pk=pk,
        owner=request.user,
    )
    credential = current_credential(ticket)
    if not credential:
        return HttpResponse("Ticket credential unavailable", status=404)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(credential)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="#111827", back_color="white").convert("RGB")
    if request.GET.get("compact"):
        image = qr_image
    else:
        image = _ticket_pass_image(ticket, qr_image)
    output = io.BytesIO()
    image.save(output, format="PNG")
    response = HttpResponse(output.getvalue(), content_type="image/png")
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="kena-ticket-{ticket.reference}.png"'
    return response


def _ticket_pass_image(ticket, qr_image):
    canvas = Image.new("RGB", (800, 1200), "white")
    draw = ImageDraw.Draw(canvas)
    font_regular = _font(28)
    font_small = _font(23)
    font_brand = _font(42, bold=True)
    font_title = _font(34, bold=True)

    draw.rectangle((0, 0, 800, 150), fill="#111827")
    _centered(draw, "Kena", 42, font_brand, "#a5b4fc")
    _centered(draw, "eTickting digital ticket", 100, font_small, "#dbeafe")

    event_lines = textwrap.wrap(ticket.event.name, width=30) or [ticket.event.name]
    y = 190
    for line in event_lines[:2]:
        _centered(draw, line, y, font_title, "#0f172a")
        y += 42

    ticket_type = ticket.ticket_category.name if ticket.ticket_category_id else "General admission"
    _centered(draw, f"Ticket type: {ticket_type}", y + 12, font_regular, "#475569")
    y += 52
    if ticket.seat_label:
        _centered(draw, f"Seat: {ticket.seat_label}", y, font_regular, "#475569")
        y += 42
    _centered(draw, f"Reference: {ticket.reference}", y + 8, font_small, "#64748b")

    qr_size = 600
    qr_image = qr_image.resize((qr_size, qr_size), Image.Resampling.NEAREST)
    qr_x = (canvas.width - qr_size) // 2
    qr_y = 390 if not ticket.seat_label else 420
    canvas.paste(qr_image, (qr_x, qr_y))
    draw.line((70, 1030, 730, 1030), fill="#e2e8f0", width=2)
    _centered(draw, "Present this code at the entrance", 1055, font_small, "#334155")
    _centered(draw, "Kena · eTickting", 1095, font_small, "#4f46e5")
    return canvas


def _font(size, bold=False):
    paths = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    )
    try:
        return ImageFont.truetype(paths, size)
    except OSError:
        return ImageFont.load_default()


def _centered(draw, text, y, font, fill):
    bounds = draw.textbbox((0, 0), text, font=font)
    draw.text(((800 - (bounds[2] - bounds[0])) / 2, y), text, font=font, fill=fill)
