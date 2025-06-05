# payments/management/commands/save_daily_payment_summary.py

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum, Q, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from payments.models import Payment, DailyPaymentSummary


class Command(BaseCommand):
    help = (
        "Compute and save the totals (cash, upi, cheque) for yesterday, "
        "and store them in DailyPaymentSummary."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help=(
                "The date for which to aggregate payments, in YYYY-MM-DD. "
                "Defaults to yesterday (relative to local date)."
            ),
        )

    def handle(self, *args, **options):
        # 1) Determine target_date (either from --date or yesterday).
        if options["date"]:
            try:
                target_date = timezone.datetime.strptime(
                    options["date"], "%Y-%m-%d"
                ).date()
            except ValueError:
                self.stderr.write("Error: --date must be in YYYY-MM-DD format.")
                return
        else:
            today = timezone.localdate()
            target_date = today - timezone.timedelta(days=1)

        self.stdout.write(f"Aggregating payments for {target_date} …")

        # 2) Filter Payment rows whose created_at__date == target_date.
        payments = Payment.objects.filter(created_at__date=target_date)

        # 3) Compute sums by method, wrapping fallback 0 as DecimalField.
        aggs = payments.aggregate(
            cash_sum=Coalesce(
                Sum(
                    "amount",
                    filter=Q(payment_method="cash")
                ),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
            upi_sum=Coalesce(
                Sum(
                    "amount",
                    filter=Q(payment_method="upi")
                ),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
            cheque_sum=Coalesce(
                Sum(
                    "amount",
                    filter=Q(payment_method="cheque")
                ),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
        )

        cash_total = aggs["cash_sum"]
        upi_total = aggs["upi_sum"]
        cheque_total = aggs["cheque_sum"]

        # 4) Upsert into DailyPaymentSummary.
        with transaction.atomic():
            summary_obj, created = DailyPaymentSummary.objects.update_or_create(
                date=target_date,
                defaults={
                    "cash_total": cash_total,
                    "upi_total": upi_total,
                    "cheque_total": cheque_total,
                },
            )

        if created:
            self.stdout.write(
                f"Created DailyPaymentSummary for {target_date}: "
                f"cash ₹{cash_total}, upi ₹{upi_total}, cheque ₹{cheque_total}."
            )
        else:
            self.stdout.write(
                f"Updated DailyPaymentSummary for {target_date}: "
                f"cash ₹{cash_total}, upi ₹{upi_total}, cheque ₹{cheque_total}."
            )
