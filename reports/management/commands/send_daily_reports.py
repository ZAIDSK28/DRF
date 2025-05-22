from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.core.mail import EmailMessage
from io import BytesIO
import pandas as pd

from bills.models import Bill
from payments.models import Payment

class Command(BaseCommand):
    help = 'Send daily Admin and DRA reports via email'

    def handle(self, *args, **options):
        today = timezone.localdate()

        # Admin entries
        admin_qs = Bill.objects.filter(created_at__date=today).values(
            'id','outlet_name','invoice_number','invoice_date',
            'amount','brand','route','assigned_to__username',
            'status','created_at'
        )
        admin_df = pd.DataFrame(list(admin_qs))

        # DRA entries
        dra_qs = Payment.objects.filter(created_at__date=today).values(
            'id','bill_id','payment_method','amount',
            'transaction_photo','cheque_type','cheque_number',
            'cheque_date','created_at'
        )
        dra_df = pd.DataFrame(list(dra_qs))

        out = BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            admin_df.to_excel(writer, sheet_name='AdminEntries', index=False)
            dra_df.to_excel(writer, sheet_name='DRAEntries', index=False)
        out.seek(0)

        subject = f'Daily Report – {today.isoformat()}'
        body    = 'Please find attached today’s Admin & DRA report.'
        recipient = 'reports@example.com'

        email = EmailMessage(subject, body,
                             settings.DEFAULT_FROM_EMAIL, [recipient])
        filename = f'daily_report_{today.isoformat()}.xlsx'
        email.attach(filename, out.read(),
                     'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        email.send()
        self.stdout.write(self.style.SUCCESS(f'Report sent to {recipient}'))
