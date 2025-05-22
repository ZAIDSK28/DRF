from django.db import models
from django.conf import settings
from bills.models import Bill

class Payment(models.Model):
    METHOD_CHOICES = (('cash','Cash'),('upi','UPI'),('cheque','Cheque'))
    bill           = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='payments')
    dra            = models.ForeignKey(settings.AUTH_USER_MODEL,
                                     limit_choices_to={'role':'dra'},
                                     on_delete=models.CASCADE)
    payment_method = models.CharField(max_length=10, choices=METHOD_CHOICES)
    amount         = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_number = models.BigIntegerField(blank=True, null=True)
    cheque_type    = models.CharField(max_length=20, blank=True, null=True)
    cheque_number  = models.CharField(max_length=50, blank=True, null=True)
    cheque_date    = models.DateField(blank=True, null=True)
    created_at     = models.DateTimeField(auto_now_add=True)
