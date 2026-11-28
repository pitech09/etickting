import base64
import json
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _decode(value):
    value = str(value).strip()
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _key_map(raw_value, setting_name, *, allow_legacy):
    try:
        values = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        if allow_legacy:
            return {"legacy": raw_value.strip()}
        raise ImproperlyConfigured(
            f"{setting_name} must be a JSON object mapping key IDs to base64 keys."
        ) from exc
    if not isinstance(values, dict):
        raise ImproperlyConfigured(
            f"{setting_name} must be a JSON object mapping key IDs to base64 keys."
        )
    return values


def credential_cipher():
    configured = getattr(settings, "TICKETING_CREDENTIAL_ENCRYPTION_KEY", "")
    if configured:
        return Fernet(configured.encode())
    derived = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(derived)


def encrypt_credential(value):
    return credential_cipher().encrypt(value.encode()).decode()


def decrypt_credential(value):
    return credential_cipher().decrypt(value.encode()).decode()


def signing_keys():
    """Read private keys from deployment secrets, never from the application database."""
    if not settings.TICKETING_SIGNING_KEYS:
        if settings.DEBUG:
            # Local development needs usable tickets without requiring a secret
            # manager. Production remains strict and must provide a deployment key.
            return {
                "development": Ed25519PrivateKey.from_private_bytes(
                    hashlib.sha256(settings.SECRET_KEY.encode()).digest()
                )
            }
        return {}
    values = _key_map(
        settings.TICKETING_SIGNING_KEYS,
        "TICKETING_SIGNING_KEYS",
        allow_legacy=settings.DEBUG,
    )
    return {
        key_id: Ed25519PrivateKey.from_private_bytes(_decode(value))
        for key_id, value in values.items()
    }


def verification_keys():
    values = {}
    if settings.TICKETING_VERIFY_KEYS:
        values.update(
            _key_map(
                settings.TICKETING_VERIFY_KEYS,
                "TICKETING_VERIFY_KEYS",
                allow_legacy=settings.DEBUG,
            )
        )
    for key_id, private_key in signing_keys().items():
        values[key_id] = base64.urlsafe_b64encode(private_key.public_key().public_bytes_raw()).decode()
    return {key_id: Ed25519PublicKey.from_public_bytes(_decode(value)) for key_id, value in values.items()}
