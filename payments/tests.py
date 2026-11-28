from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from finance.models import CommissionTransaction, RefundCommissionAdjustment
from finance.services import create_payout, initiate_payout, organisation_earnings, settle_payout
from organisations.models import Organisation, OrganisationMembership
from orders.models import Order
from ticketing.models import Event, Ticket

from .models import Payment, RefundRequest
from .services import (
    complete_refund,
    create_event_cancellation_refunds,
    request_refund,
    review_refund,
    start_refund_processing,
)


class RefundWorkflowTests(TestCase):
    def setUp(self):
        self.organisation = Organisation.objects.create(name="Refund Org", slug="refund-org")
        self.customer = User.objects.create_user(email="refund-customer@example.com", password="password")
        self.other_customer = User.objects.create_user(email="other-customer@example.com", password="password")
        self.organiser = User.objects.create_user(email="refund-organiser@example.com", password="password")
        OrganisationMembership.objects.create(
            organisation=self.organisation, user=self.organiser,
            role=OrganisationMembership.Role.OWNER,
        )
        self.event = Event.objects.create(
            organisation=self.organisation, name="Refund Event", starts_at=timezone.now(),
        )

    def make_paid_order(self, *, customer=None, total="100.00", commission_rate=None):
        customer = customer or self.customer
        order = Order.objects.create(
            customer=customer, event=self.event, status=Order.Status.PAID,
            subtotal_minor=total, total_minor=total, commission_rate=commission_rate,
            commission_minor=Decimal("10.00") if commission_rate else Decimal("0.00"),
        )
        payment = Payment.objects.create(
            order=order, provider=Payment.Provider.MPESA,
            status=Payment.Status.SUCCESSFUL, amount_minor=total,
            provider_reference=f"PAY-{order.pk}",
        )
        return order, payment

    def approve_and_process(self, refund):
        review_refund(
            refund_id=refund.pk, reviewer=self.organiser, decision="approve",
        )
        start_refund_processing(refund_id=refund.pk, actor=self.organiser)

    def test_unpaid_order_and_other_customer_cannot_request(self):
        order = Order.objects.create(
            customer=self.customer, event=self.event, total_minor="100.00",
        )
        with self.assertRaises(ValueError):
            request_refund(order_id=order.pk, requester=self.customer, amount_minor="10.00", reason="Cannot attend")
        paid_order, _payment = self.make_paid_order()
        with self.assertRaises(PermissionDenied):
            request_refund(order_id=paid_order.pk, requester=self.other_customer, amount_minor="10.00", reason="Not mine")

    def test_refund_request_reserves_amount_and_approval_requires_reason_on_rejection(self):
        order, _payment = self.make_paid_order()
        first = request_refund(order_id=order.pk, requester=self.customer, amount_minor="60.00", reason="Change of plans")
        with self.assertRaises(ValueError):
            request_refund(order_id=order.pk, requester=self.customer, amount_minor="41.00", reason="Too much")
        with self.assertRaises(ValueError):
            review_refund(refund_id=first.pk, reviewer=self.organiser, decision="reject")
        review_refund(refund_id=first.pk, reviewer=self.organiser, decision="reject", note="Policy does not cover this reason")
        second = request_refund(order_id=order.pk, requester=self.customer, amount_minor="40.00", reason="Second request")
        self.assertEqual(second.requested_amount_minor, Decimal("40.00"))

    def test_partial_completion_preserves_ticket_and_full_completion_refunds_it(self):
        order, _payment = self.make_paid_order()
        ticket = Ticket.objects.create(
            reference="REFUND-TICKET-1", credential_hash="refund-credential-1",
            event=self.event, owner=self.customer, order=order,
        )
        partial = request_refund(order_id=order.pk, requester=self.customer, amount_minor="20.00", reason="Partial")
        review_refund(refund_id=partial.pk, reviewer=self.organiser, decision="approve")
        start_refund_processing(refund_id=partial.pk, actor=self.organiser)
        complete_refund(refund_id=partial.pk, actor=self.organiser, provider_reference="REF-20")
        ticket.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.ISSUED)
        self.assertEqual(order.status, Order.Status.PAID)
        full = request_refund(order_id=order.pk, requester=self.customer, amount_minor="80.00", reason="Full remainder")
        self.approve_and_process(full)
        complete_refund(refund_id=full.pk, actor=self.organiser, provider_reference="REF-80")
        ticket.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.REFUNDED)
        self.assertEqual(order.status, Order.Status.REFUNDED)

    def test_cancellation_entitlement_is_idempotent_and_only_paid_orders_are_eligible(self):
        paid, _payment = self.make_paid_order()
        Order.objects.create(customer=self.customer, event=self.event, total_minor="50.00")
        first = create_event_cancellation_refunds(event=self.event, actor=self.organiser)
        second = create_event_cancellation_refunds(event=self.event, actor=self.organiser)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(RefundRequest.objects.filter(order=paid, is_event_cancellation=True).count(), 1)
        self.assertEqual(first[0].notification_status, RefundRequest.NotificationStatus.SENT)

    def test_commission_reversal_is_historical_and_idempotent_with_recovery(self):
        order, payment = self.make_paid_order(total="100.00", commission_rate="10.00")
        commission = CommissionTransaction.objects.create(
            order=order, payment=payment, organisation=self.organisation, event=self.event,
            gross_ticket_sales_minor="100.00", commission_rate="10.00",
            commission_minor="10.00", organiser_net_minor="90.00",
        )
        payout = create_payout(organisation=self.organisation, amount_minor="90.00", idempotency_key="refund-payout-1")
        initiate_payout(payout_id=payout.pk)
        settle_payout(payout_id=payout.pk, provider_reference="BANK-REFUND-1")
        refund = request_refund(order_id=order.pk, requester=self.customer, amount_minor="100.00", reason="Cancelled")
        self.approve_and_process(refund)
        complete_refund(refund_id=refund.pk, actor=self.organiser, provider_reference="REF-100")
        adjustment = RefundCommissionAdjustment.objects.get(refund=refund)
        self.assertEqual(adjustment.commission_reversal_minor, Decimal("10.00"))
        self.assertEqual(adjustment.organiser_recovery_minor, Decimal("90.00"))
        self.assertEqual(RefundCommissionAdjustment.objects.count(), 1)
        earnings = organisation_earnings(organisation=self.organisation)
        self.assertEqual(earnings["commission_reversals_minor"], Decimal("10.00"))
        self.assertEqual(earnings["organiser_recovery_minor"], Decimal("90.00"))
