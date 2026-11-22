import base64
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from django.conf import settings


def _decode(value):
    return base64.urlsafe_b64decode(value.encode())


def signing_keys():
    """Read private keys from deployment secrets, never from the application database."""
    if not settings.TICKETING_SIGNING_KEYS:
        return {}
    return {key_id: Ed25519PrivateKey.from_private_bytes(_decode(value)) for key_id, value in json.loads(settings.TICKETING_SIGNING_KEYS).items()}


def verification_keys():
    values = {}
    if settings.TICKETING_VERIFY_KEYS:
        values.update(json.loads(settings.TICKETING_VERIFY_KEYS))
    for key_id, private_key in signing_keys().items():
        values[key_id] = base64.urlsafe_b64encode(private_key.public_key().public_bytes_raw()).decode()
    return {key_id: Ed25519PublicKey.from_public_bytes(_decode(value)) for key_id, value in values.items()}
