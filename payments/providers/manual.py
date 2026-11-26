"""Manual mobile-money adapters.

These adapters deliberately never claim that a payment was verified. They
provide a stable provider boundary for the current human-verification flow;
future API adapters can use the same PaymentProvider interface independently.
"""

from .base import PaymentProvider


class ManualMobileMoneyProvider(PaymentProvider):
    automated = False

    def initiate(self, order, amount, currency="LSL", callback_url=None):
        return {
            "provider_reference": "",
            "payment_url": None,
            "raw_response": {"mode": "manual", "provider": self.name},
            "extra_context": {
                "amount": amount,
                "currency": currency,
                "instructions": "Pay using the displayed receiving number, then submit the transaction reference for manual verification.",
            },
        }

    def verify(self, provider_reference, callback_data=None):
        return False

    def refund(self, payment, amount=None):
        raise NotImplementedError("Manual mobile-money refunds require an operator and provider confirmation")

    def verify_webhook_signature(self, request):
        return False


class ManualMpesaProvider(ManualMobileMoneyProvider):
    name = "mpesa"


class ManualEcocashProvider(ManualMobileMoneyProvider):
    name = "ecocash"
