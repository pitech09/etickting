from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from organisations.models import Organisation
from ticketing.models import Event, Ticket

from .services import mint_ticket


class BlockchainTests(TestCase):
    def test_minting_fails_closed_without_deployment_credentials(self):
        user = User.objects.create_user(email="chain@example.com", password="test-pass-123")
        organisation = Organisation.objects.create(name="Chain Org", slug="chain-org")
        event = Event.objects.create(organisation=organisation, name="Chain Event", starts_at=timezone.now())
        ticket = Ticket.objects.create(event=event, owner=user, reference="CHAIN-1")
        with override_settings(BLOCKCHAIN_RPC_URL="", BLOCKCHAIN_CONTRACT_ADDRESS="", BLOCKCHAIN_PRIVATE_KEY=""):
            with self.assertRaisesMessage(ValidationError, "Blockchain minting is not configured"):
                mint_ticket(ticket=ticket)
