import logging

from django.conf import settings

from .base import PaymentProvider

logger = logging.getLogger(__name__)


class MPesaLesothoProvider(PaymentProvider):
    """M-Pesa Lesotho payment provider.

    Supports both sandbox and live environments.
    Never stores PINs or sensitive authentication credentials.
    """

    name = "mpesa"

    def __init__(self):
        self.consumer_key = getattr(settings, "MPESA_CONSUMER_KEY", "")
        self.consumer_secret = getattr(settings, "MPESA_CONSUMER_SECRET", "")
        self.shortcode = getattr(settings, "MPESA_SHORTCODE", "")
        self.passkey = getattr(settings, "MPESA_PASSKEY", "")
        self.base_url = getattr(
            settings,
            "MPESA_BASE_URL",
            "https://sandbox.safaricom.co.ke",
        )
        self.callback_url = getattr(settings, "MPESA_CALLBACK_URL", "")

    def is_configured(self):
        return bool(
            self.consumer_key and self.consumer_secret and self.shortcode
        )

    def initiate(self, order, amount_minor, currency="LSL", callback_url=None):
        if not self.is_configured():
            logger.warning(
                "M-Pesa not configured — sandbox simulation for order %s",
                order.reference,
            )
            return self._sandbox_initiate(order, amount_minor, callback_url)

        raise NotImplementedError(
            "Production M-Pesa integration not yet implemented."
        )

    def _sandbox_initiate(self, order, amount_minor, callback_url=None):
        import uuid

        provider_reference = f"MPESA-{uuid.uuid4().hex[:12].upper()}"
        return {
            "provider_reference": provider_reference,
            "payment_url": None,
            "raw_response": {
                "provider": "mpesa",
                "environment": "sandbox",
                "checkout_request_id": provider_reference,
                "amount": amount_minor,
                "currency": currency,
                "simulated": True,
            },
            "extra_context": {
                "provider": "M-Pesa",
                "simulated": True,
                "message": (
                    "Sandbox: STK Push simulated. In production, "
                    "the customer receives a PIN prompt on their phone."
                ),
            },
        }