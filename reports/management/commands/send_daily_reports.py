import datetime
import logging
from io import BytesIO

import openpyxl
import pandas as pd
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.utils import timezone

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
        " 9) Overdue Days"
    )

    def handle(self, *args, **options):
        """
        1. Determine “today” in the active timezone.
        2. Query all Payment objects created today, along with related Bill and User.
        3. Build a DataFrame with exactly the nine columns requested.
        4. Compute “Overdue Days” as max((today – invoice_date).days, 0).
        5. If no payments, log & exit without emailing.
        6. Otherwise, write to an in-memory Excel file (one sheet), and email it to
           settings.DAILY_REPORT_RECIPIENTS (a list in Django settings).
        """

        # 1. Today’s date in local timezone
        today = timezone.localdate()

        # 2. Fetch payments created today, along with related Bill and DRA user.
        #    Adjust 'created_by' below to match your actual field on Payment for “DRA username.”
        payments_qs = (
            Payment.objects
                .filter(created_at__date=today)
                .select_related('bill', 'dra')
                .order_by('created_at')
        )

        if not payments_qs.exists():
            msg = f"No payments found for {today.isoformat()}; skipping email."
            self.stdout.write(self.style.WARNING(msg))
            logger.info(msg)
            return

        # 3. Build a list of dicts, one per payment, with the nine desired fields
        rows = []
        for p in payments_qs:
            bill = p.bill
            # Ensure bill and user exist (guard against nulls if your FK is nullable)
            if not bill:
                # If somehow a Payment has no related Bill, skip or handle as needed
                continue

            # Compute overdue days: if invoice_date is in past, otherwise 0
            # Note: invoice_date is assumed date or datetime.datetime; convert if needed
            invoice_date = bill.invoice_date
            if invoice_date is None:
                overdue_days = ""
            else:
                # If invoice_date is a datetime, convert to date
                if isinstance(invoice_date, datetime.datetime):
                    invoice_date = invoice_date.date()
                delta = today - invoice_date
                overdue_days = delta.days if delta.days > 0 else 0

            # DRA username: adjust `created_by.username` if your Payment model uses a different field
            dra_username = getattr(p.dra, "username", "")

            rows.append({
                "Bill ID":           bill.id,
                "Brand":             bill.brand,
                "Invoice Date":      invoice_date,
                "Route Name":        bill.route,
                "Invoice Number":    bill.invoice_number,
                "Outlet Name":       bill.outlet,
                "Payment Amount":    p.amount,
                "Username":          dra_username,
                "Overdue Days":      overdue_days,
            })

        # Convert to DataFrame, enforcing column order
        df = pd.DataFrame(rows, columns=[
            "Bill ID",
            "Brand",
            "Invoice Date",
            "Route Name",
            "Invoice Number",
            "Outlet Name",
            "Payment Amount",
            "Username",
            "Overdue Days",
        ])

        # 4. (Optional) If you want to format “Invoice Date” as YYYY-MM-DD strings for Excel:
        #    df['Invoice Date'] = df['Invoice Date'].apply(lambda d: d.isoformat() if hasattr(d, 'isoformat') else "")

        # 5. Write the DataFrame to an in-memory XLSX
        out = BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            # You could set date and number formats here if desired
            df.to_excel(writer, index=False, sheet_name="DailyPaymentsReport")
            workbook = writer.book
            sheet = writer.sheets["DailyPaymentsReport"]

            # Example: Auto-adjust column widths (optional)
            for idx, column in enumerate(df.columns, 1):
                # Compute a reasonable width: max length between header & any cell in that column
                max_length = max(
                    [len(str(column))] +
                    [len(str(v)) for v in df[column].values]
                ) + 2
                sheet.column_dimensions[
                    openpyxl.utils.get_column_letter(idx)
                ].width = max_length

        out.seek(0)

        # 6. Build and send email
        subject = f"Daily Payments Report: {today.isoformat()}"
        body = (
            "Hello,\n\n"
            f"Attached is the daily payments report for {today.isoformat()}, "
            "containing Bill ID, Brand, Invoice Date, Route Name, Invoice Number, "
            "Outlet Name, Payment Amount, Username, and Overdue Days.\n\n"
            "Regards,\n"
            "Auto-Reporter"
        )

        recipients = getattr(
            settings, "DAILY_REPORT_RECIPIENTS", []
        )
        if not recipients:
            err = "DAILY_REPORT_RECIPIENTS not set in settings.py; cannot send report."
            self.stderr.write(self.style.ERROR(err))
            logger.error(err)
            return

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )

        filename = f"daily_payments_{today.isoformat()}.xlsx"
        email.attach(
            filename,
            out.read(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        try:
            email.send(fail_silently=False)
            success_msg = f"Sent daily payments report for {today.isoformat()} to {recipients}"
            self.stdout.write(self.style.SUCCESS(success_msg))
            logger.info(success_msg)
        except Exception as e:
            err_msg = f"Failed to send daily payments report: {e}"
            self.stderr.write(self.style.ERROR(err_msg))
            logger.exception(err_msg)
