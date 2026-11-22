from django.core.exceptions import ValidationError

from .models import TicketOwnershipProof


def create_proof(*, ticket, network="polygon"):
    """Create a reconciliation record; no chain claim is made without Web3 credentials."""
    if not network:
        raise ValidationError("A blockchain network is required")
    return TicketOwnershipProof.objects.get_or_create(ticket=ticket, defaults={"network": network})[0]


def mint_ticket(*, ticket):
    """Fail closed until a deployed contract, RPC endpoint and signing key exist."""
    from django.conf import settings

    missing = [name for name, value in (("BLOCKCHAIN_RPC_URL", settings.BLOCKCHAIN_RPC_URL), ("BLOCKCHAIN_CONTRACT_ADDRESS", settings.BLOCKCHAIN_CONTRACT_ADDRESS), ("BLOCKCHAIN_PRIVATE_KEY", settings.BLOCKCHAIN_PRIVATE_KEY)) if not value]
    if missing:
        raise ValidationError(f"Blockchain minting is not configured: {', '.join(missing)}")
    raise ValidationError("Blockchain provider adapter is not enabled; reconcile through the approved Web3 worker")
