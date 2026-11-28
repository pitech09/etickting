from decimal import Decimal
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from organisations.models import Organisation, OrganisationMembership
from orders.models import Order
from django.utils import timezone

from payments.models import Payment
from .models import CommissionTransaction, LedgerEntry, Payout, PlatformCommissionConfig
from .services import calculate_commission, create_payout, initiate_payout, organisation_earnings, record_balanced_transaction, record_commission_for_payment, settle_payout


class FinanceTests(TestCase):
    def test_commission_uses_decimal_arithmetic(self):
        self.assertEqual(calculate_commission("10000.00", "10.00"), Decimal("1000.00"))
        self.assertEqual(calculate_commission("100.01", "10.00"), Decimal("10.00"))

    def test_commission_rate_changes_do_not_recalculate_existing_order_snapshot(self):
        first = PlatformCommissionConfig.current()
        first.commission_rate = "10.00"
        first.save(update_fields=["commission_rate", "updated_at"])
        organisation = Organisation.objects.create(name="Commission Org", slug="commission-org")
        customer = User.objects.create_user(email="commission-buyer@example.com", password="pass-12345")
        event = organisation.events.create(name="Commission Event", starts_at=timezone.now())
        first_order = Order.objects.create(
            customer=customer, event=event, status=Order.Status.PAID,
            subtotal_minor="100.00", total_minor="100.00", commission_rate=first.commission_rate,
            commission_minor="10.00", organiser_net_minor="90.00",
        )
        first.commission_rate = "12.50"
        first.save(update_fields=["commission_rate", "updated_at"])
        first_order.refresh_from_db()
        self.assertEqual(first_order.commission_rate, Decimal("10.00"))
        self.assertEqual(calculate_commission("100.00", first.commission_rate), Decimal("12.50"))

    def test_successful_sale_creates_one_idempotent_commission_snapshot(self):
        organisation = Organisation.objects.create(name="Commission Sales", slug="commission-sales")
        customer = User.objects.create_user(email="sale-buyer@example.com", password="pass-12345")
        event = organisation.events.create(name="Commission Sale", starts_at=timezone.now())
        order = Order.objects.create(
            customer=customer, event=event, status=Order.Status.PAID,
            subtotal_minor="100.00", total_minor="100.00", commission_rate="10.00",
            commission_minor="10.00", organiser_net_minor="90.00",
        )
        payment = Payment.objects.create(
            order=order, provider=Payment.Provider.MPESA,
            status=Payment.Status.SUCCESSFUL, amount_minor="100.00",
            provider_reference="COMMISSION-1",
        )
        first = record_commission_for_payment(payment=payment, order=order)
        second = record_commission_for_payment(payment=payment, order=order)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(CommissionTransaction.objects.get(pk=first.pk).commission_minor, Decimal("10.00"))

    def test_balanced_transaction_is_idempotent(self):
        organisation = Organisation.objects.create(name="Finance Org", slug="finance-org")
        first = record_balanced_transaction(organisation=organisation, reference="TX-1", description="Ticket sale", idempotency_key="payment-1", debit_account="cash", credit_account="ticket-sales", amount_minor=Decimal("10.00"))
        second = record_balanced_transaction(organisation=organisation, reference="TX-2", description="Duplicate", idempotency_key="payment-1", debit_account="cash", credit_account="ticket-sales", amount_minor=Decimal("10.00"))
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(LedgerEntry.objects.filter(transaction=first).count(), 2)

    def test_earnings_include_refunds_and_payout_balance(self):
        organisation = Organisation.objects.create(name="Settlement Org", slug="settlement-org")
        customer = User.objects.create_user(email="finance-buyer@example.com", password="pass-12345")
        event = organisation.events.create(name="Finance Event", starts_at=timezone.now())
        Order.objects.create(customer=customer, event=event, status=Order.Status.PAID, total_minor="100.00", fee_minor="5.00")
        Order.objects.create(customer=customer, event=event, status=Order.Status.REFUNDED, total_minor="20.00", fee_minor="1.00")
        self.assertEqual(organisation_earnings(organisation=organisation)["payable_minor"], Decimal("94.00"))
        payout = create_payout(organisation=organisation, amount_minor=Decimal("94.00"), idempotency_key="settlement-1")
        self.assertEqual(Payout.objects.count(), 1)
        self.assertEqual(payout.status, Payout.Status.PENDING)
        initiate_payout(payout_id=payout.pk)
        settle_payout(payout_id=payout.pk, provider_reference="BANK-1")
        self.assertEqual(organisation_earnings(organisation=organisation)["payable_minor"], Decimal("0.00"))

    def test_event_payout_is_attributed_and_cannot_exceed_organisation_balance(self):
        organisation = Organisation.objects.create(name="Event Settlement Org", slug="event-settlement-org")
        customer = User.objects.create_user(email="event-settlement-buyer@example.com", password="pass-12345")
        event = organisation.events.create(name="Settlement Event", starts_at=timezone.now())
        Order.objects.create(customer=customer, event=event, status=Order.Status.PAID, total_minor="100.00")

        payout = create_payout(
            organisation=organisation,
            event=event,
            amount_minor="100.00",
            idempotency_key="event-settlement-1",
            request_note="Post-event settlement",
        )

        self.assertEqual(payout.event, event)
        self.assertEqual(payout.request_note, "Post-event settlement")
        self.assertEqual(organisation_earnings(organisation=organisation, event=event)["payable_minor"], Decimal("100.00"))
        with self.assertRaisesMessage(ValueError, "Payout exceeds the organisation's payable balance"):
            create_payout(
                organisation=organisation,
                event=event,
                amount_minor="0.01",
                idempotency_key="event-settlement-2",
            )

    def test_event_report_and_payout_request_are_manager_scoped(self):
        organisation = Organisation.objects.create(name="Event Report Org", slug="event-report-org")
        manager = User.objects.create_user(email="settlement-manager@example.com", password="pass-12345")
        staff = User.objects.create_user(email="settlement-staff@example.com", password="pass-12345")
        OrganisationMembership.objects.create(organisation=organisation, user=manager, role=OrganisationMembership.Role.EVENT_MANAGER)
        OrganisationMembership.objects.create(organisation=organisation, user=staff, role=OrganisationMembership.Role.EVENT_STAFF)
        customer = User.objects.create_user(email="settlement-report-buyer@example.com", password="pass-12345")
        event = organisation.events.create(name="Reportable Event", starts_at=timezone.now())
        Order.objects.create(customer=customer, event=event, status=Order.Status.PAID, total_minor="50.00")

        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("finance:event-report", args=[event.pk])).status_code, 404)
        self.client.force_login(manager)
        response = self.client.post(reverse("finance:event-payout-request", args=[event.pk]), {
            "amount_maloti": "50.00", "request_key": "request-1", "request_note": "Event close-out",
        })

        self.assertRedirects(response, reverse("finance:event-report", args=[event.pk]))
        payout = Payout.objects.get(event=event)
        self.assertEqual(payout.requested_by, manager)
        self.assertEqual(payout.amount_minor, Decimal("50.00"))
