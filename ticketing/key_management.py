import base64
import json
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.fernet import Fernet
from django.conf import settings


def _decode(value):
    return base64.urlsafe_b64decode(value.encode())


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
    return {key_id: Ed25519PrivateKey.from_private_bytes(_decode(value)) for key_id, value in json.loads(settings.TICKETING_SIGNING_KEYS).items()}


def verification_keys():
    values = {}
    if settings.TICKETING_VERIFY_KEYS:
        values.update(json.loads(settings.TICKETING_VERIFY_KEYS))
    for key_id, private_key in signing_keys().items():
        values[key_id] = base64.urlsafe_b64encode(private_key.public_key().public_bytes_raw()).decode()
    return {key_id: Ed25519PublicKey.from_public_bytes(_decode(value)) for key_id, value in values.items()}
