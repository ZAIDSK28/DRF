import datetime
import logging
from io import BytesIO

import openpyxl
import pandas as pd
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models.functions import Coalesce
from django.db.models import Sum, Value, DecimalField, Q

from bills.models import Bill
from payments.models import Payment

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Compile today’s payments with their related Bill info, "
        "compute Overdue Days, and email an Excel file containing:\n"
        " 1) Bill ID\n"
        " 2) Brand\n"
        " 3) Invoice Date\n"
        " 4) Route Name\n"
        " 5) Invoice Number\n"
        " 6) Outlet Name\n"
        " 7) Payment Amount\n"
        " 8) Username\n"
        " 9) Overdue Days\n"
        "10) Created At (timestamp)\n\n"
        "And at the top: Today’s cash/UPI/cheque+electronic cleared totals."
    )

    def handle(self, *args, **options):
        # 1) Today’s date
        today = timezone.localdate()

        # 2) Fetch payments created today
        payments_qs = (
            Payment.objects
                   .filter(created_at__date=today)
                   .select_related('bill', 'dra')
                   .order_by('created_at')
        )

        if not payments_qs.exists():
            msg = f"No payments found for {today}; skipping email."
            self.stdout.write(self.style.WARNING(msg))
            logger.info(msg)
            return

        # 3) Compute today’s totals
        cash_total = Payment.objects.filter(
            payment_method='cash',
            created_at__date=today
        ).aggregate(
            total=Coalesce(
                Sum('amount'),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
            )
        )['total']

        upi_total = Payment.objects.filter(
            payment_method='upi',
            created_at__date=today
        ).aggregate(
            total=Coalesce(
                Sum('amount'),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
            )
        )['total']

        cheque_total = Payment.objects.filter(
            payment_method__in=['cheque', 'electronic'],
            cheque_status='cleared',
            cheque_date=today
        ).aggregate(
            total=Coalesce(
                Sum('amount'),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
            )
        )['total']

        # 4) Build rows for each payment
        rows = []
        for p in payments_qs:
            bill = p.bill
            if not bill:
                continue

            inv_date = bill.invoice_date
            if isinstance(inv_date, datetime.datetime):
                inv_date = inv_date.date()
            overdue = max((today - inv_date).days, 0) if inv_date else ''

            rows.append({
                "Bill ID":        bill.id,
                "Brand":          bill.brand,
                "Invoice Date":   inv_date,
                "Route Name":     bill.route.name,
                "Invoice Number": bill.invoice_number,
                "Outlet Name":    bill.outlet.name,
                "Payment Amount": p.amount,
                "Username":       p.dra.username if p.dra else '',
                "Overdue Days":   overdue,
                # Option A: convert to tz-naive datetime
                "Created At": p.created_at.astimezone(timezone.get_current_timezone()).replace(tzinfo=None),
            })

        df = pd.DataFrame(rows, columns=[
            "Bill ID","Brand","Invoice Date","Route Name",
            "Invoice Number","Outlet Name","Payment Amount",
            "Username","Overdue Days","Created At"
        ])

        # 5) Write to in-memory Excel
        out = BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            # Create the sheet and get handle
            workbook = writer.book
            sheet = workbook.create_sheet("DailyPaymentsReport", 0)

            # Totals header row
            sheet.append([
                "Cash Total",     float(cash_total),
                "UPI Total",      float(upi_total),
                "Cheque Total",   float(cheque_total),
            ])
            sheet.append([])  # blank row

            # Write column headers + rows
            for r in openpyxl.utils.dataframe.dataframe_to_rows(df, index=False, header=True):
                sheet.append(r)

            # Auto‐width
            for idx, col in enumerate(df.columns, 1):
                max_len = max(
                    len(str(col)),
                    *(len(str(cell)) for cell in df[col].values)
                ) + 2
                sheet.column_dimensions[
                    openpyxl.utils.get_column_letter(idx)
                ].width = max_len

        out.seek(0)

        # 6) Email it
        recipients = getattr(settings, "DAILY_REPORT_RECIPIENTS", [])
        if not recipients:
            err = "DAILY_REPORT_RECIPIENTS not set; cannot send report."
            self.stderr.write(self.style.ERROR(err))
            logger.error(err)
            return

        subject = f"Daily Payments Report: {today}"
        body = (
            f"Attached is the payments report for {today}, including "
            "per‐payment details (with Created At) and today’s totals.\n"
        )
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        filename = f"daily_payments_{today}.xlsx"
        email.attach(
            filename,
            out.read(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        try:
            email.send(fail_silently=False)
            ok = f"Sent daily report to {recipients}"
            self.stdout.write(self.style.SUCCESS(ok))
            logger.info(ok)
        except Exception as e:
            err = f"Failed to send report: {e}"
            self.stderr.write(self.style.ERROR(err))
            logger.exception(err)