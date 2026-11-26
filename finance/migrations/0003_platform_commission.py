from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("finance", "0002_payout_settlement_fields"),
        ("orders", "0004_order_commission_snapshot"),
        ("payments", "0004_manual_payment_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformCommissionConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("commission_rate", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal("0.00")), django.core.validators.MaxValueValidator(Decimal("100.00"))])),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="CommissionTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("gross_ticket_sales_minor", models.PositiveIntegerField()),
                ("commission_rate", models.DecimalField(decimal_places=2, max_digits=5)),
                ("commission_minor", models.PositiveIntegerField()),
                ("provider_cost_minor", models.PositiveIntegerField(default=0)),
                ("organiser_net_minor", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="commission_transactions", to="ticketing.event")),
                ("organisation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="commission_transactions", to="organisations.organisation")),
                ("order", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="commission_transaction", to="orders.order")),
                ("payment", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="commission_transaction", to="payments.payment")),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
