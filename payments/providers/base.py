import uuid
from abc import ABC, abstractmethod

from payments.models import Payment


class PaymentProvider(ABC):
    """Abstract base class for payment providers.

    Concrete providers implement:
    - initiate(order, amount, callback_url) -> dict with provider-specific fields
    - verify(provider_reference, response_data) -> bool
    - refund(payment, amount) -> dict

    The provider name is used for registry lookup and must match
    Payment.Provider choices.
    """

    name = None  # Must be set by subclasses

    @abstractmethod
    def initiate(self, order, amount, currency="LSL", callback_url=None):
        """Initiate a payment with the provider.

        Returns a dict with:
        - provider_reference: str
        - payment_url: str (where customer should be redirected)
        - raw_response: dict (provider response for audit)
        - extra_context: dict (template context, optional)
        """
        raise NotImplementedError

    @abstractmethod
    def verify(self, provider_reference, callback_data=None):
        """Verify a payment callback from the provider.

        Returns True if the payment is confirmed successful,
        False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    def refund(self, payment, amount=None):
        """Refund a payment.

        Returns a dict with refund details.
        """
        raise NotImplementedError

    @abstractmethod
    def verify_webhook_signature(self, request):
        """Verify an incoming webhook signature.

        Returns True if valid, False otherwise.
        """
        raise NotImplementedError

    def generate_idempotency_key(self):
        return f"{self.name}-{uuid.uuid4().hex[:16]}"
