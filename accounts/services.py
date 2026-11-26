import hashlib
import json
import logging
import re
import secrets
import urllib.error
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.utils import timezone

from .models import User

logger = logging.getLogger(__name__)


def normalize_phone(value):
    """Return a conservative E.164 number for Lesotho or an explicit country code."""
    value = re.sub(r"[\s().-]", "", (value or "").strip())
    if value.startswith("00"):
        value = "+" + value[2:]
    if value.startswith("0"):
        value = "+266" + value[1:]
    if not re.fullmatch(r"\+[1-9]\d{7,14}", value):
        raise ValueError("Enter a valid phone number, for example +266 5XXX XXXX.")
    return value


def _rate_key(purpose, phone, ip_address):
    digest = hashlib.sha256(f"{purpose}:{phone}:{ip_address}".encode()).hexdigest()
    return f"otp-request:{digest}"


def _send_textbee_sms(*, phone, message):
    if not settings.TEXTBEE_API_KEY or not settings.TEXTBEE_DEVICE_ID:
        logger.error("TextBee SMS is not configured")
        return False
    payload = json.dumps({
        "recipients": [phone],
        "message": message,
        "deviceId": settings.TEXTBEE_DEVICE_ID,
    }).encode()
    request = urllib.request.Request(
        settings.TEXTBEE_API_URL,
        data=payload,
        headers={"Content-Type": "application/json", "x-api-key": settings.TEXTBEE_API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if not 200 <= response.status < 300:
                logger.warning("TextBee rejected SMS with status %s", response.status)
                return False
            return True
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("TextBee SMS delivery failed: %s", exc.__class__.__name__)
        return False


def issue_otp(*, user, phone, purpose, ip_address=""):
    from .models import PhoneOTP

    phone = normalize_phone(phone)
    cache_key = _rate_key(purpose, phone, ip_address or "unknown")
    request_count = cache.get(cache_key, 0)
    if request_count >= settings.OTP_REQUESTS_PER_HOUR:
        raise ValueError("Too many code requests. Please try again later.")
    cache.set(cache_key, request_count + 1, 3600)
    PhoneOTP.objects.filter(user=user, purpose=purpose, consumed_at__isnull=True).update(
        consumed_at=timezone.now()
    )
    code = f"{secrets.randbelow(1_000_000):06d}"
    otp = PhoneOTP.objects.create(
        user=user,
        phone_number=phone,
        purpose=purpose,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
    )
    sent = _send_textbee_sms(
        phone=phone,
        message=f"Kena code: {code}. It expires in {settings.OTP_EXPIRY_MINUTES} minutes. Do not share it.",
    )
    if not sent:
        otp.delete()
        raise ValueError("SMS delivery is temporarily unavailable. Please try again later.")
    return otp


def verify_otp(*, user, code, purpose, phone=None):
    from .models import PhoneOTP

    query = {"user": user, "purpose": purpose, "consumed_at__isnull": True}
    if phone:
        query["phone_number"] = normalize_phone(phone)
    otp = PhoneOTP.objects.filter(**query).order_by("-created_at").first()
    if not otp or otp.expires_at <= timezone.now() or otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        return False
    otp.attempts += 1
    valid = check_password((code or "").strip(), otp.code_hash)
    if valid:
        otp.consumed_at = timezone.now()
    otp.save(update_fields=["attempts", "consumed_at"])
    return valid


def find_verified_phone_user(phone):
    try:
        phone = normalize_phone(phone)
    except ValueError:
        return None
    return User.objects.filter(phone_number=phone, phone_verified_at__isnull=False, is_active=True).first()
