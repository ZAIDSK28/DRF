from django.core.management.base import BaseCommand
from django.utils import timezone
from bills.models import Bill

class Command(BaseCommand):
    help = "Recalculate overdue_days for all open bills"

    def handle(self, *args, **opts):
        today = timezone.localdate()
        qs = Bill.objects.filter(status='open')
        for bill in qs:
            bill.overdue_days = (today - bill.created_at.date()).days
            bill.save(update_fields=['overdue_days'])
        self.stdout.write(self.style.SUCCESS(
            f"Updated {qs.count()} open bills’ overdue_days."
        ))
