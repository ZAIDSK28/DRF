from django.db import models
from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db.models import Sum
from decimal import Decimal
from bills.models import Bill

class Payment(models.Model):
    METHOD_CHOICES = (('cash','Cash'),('upi','UPI'),('cheque','Cheque'),('electronic','Electronic'))
    FIRM_CHOICES = [
        ('NA', 'NA'),
        ('MZ', 'MZ'),
    ]
    CHEQUE_STATUS = [
      ('pending', 'Pending'),
      ('bounced', 'Bounced'),
      ('cleared', 'Cleared'),
    ]

    bill           = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='user_payments')
    dra            = models.ForeignKey(settings.AUTH_USER_MODEL,
                                     limit_choices_to={'role':'dra'},
                                     on_delete=models.CASCADE)
    payment_method = models.CharField(max_length=10, choices=METHOD_CHOICES)
    amount         = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_number = models.BigIntegerField(blank=True, null=True)
    cheque_type    = models.CharField(max_length=20, blank=True, null=True)
    cheque_number  = models.CharField(max_length=50, blank=True, null=True)
    cheque_date    = models.DateField(blank=True, null=True)
    firm           = models.CharField(max_length=2, choices=FIRM_CHOICES, default='NA')
    cheque_status = models.CharField(max_length=10, choices=CHEQUE_STATUS,default='pending')
    created_at     = models.DateTimeField(auto_now_add=True)

@receiver(post_save, sender=Payment)
def update_bill_remaining(sender, instance, **kwargs):
    bill = instance.bill
    paid = bill.user_payments.aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    bill.remaining_amount = bill.actual_amount - paid
    if bill.remaining_amount <= 0:
        bill.status = 'closed'
    bill.save(update_fields=['remaining_amount', 'status'])

class DailyPaymentSummary(models.Model):
    date = models.DateField(unique=True)  # e.g. 2025-06-04
    cash_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    upi_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    cheque_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    class Meta:
        ordering = ["-date"]
        verbose_name = "Daily Payment Summary"
        verbose_name_plural = "Daily Payment Summaries"

    def __str__(self):
        return f"{self.date}: ₹{self.cash_total} cash | ₹{self.upi_total} UPI | ₹{self.cheque_total} cheque"
