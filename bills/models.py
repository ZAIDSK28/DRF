from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal


class Route(models.Model):
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Outlet(models.Model):
    name  = models.CharField(max_length=255)
    route = models.ForeignKey(Route, related_name="outlets",
                              on_delete=models.CASCADE)

    class Meta:
        unique_together = ("name", "route")
        ordering = ("route__name", "name")

    def __str__(self):
        return f"{self.name} — {self.route}"




class Bill(models.Model):
    STATUS_CHOICES = (('open','Open'),('cleared','Cleared'))

    overdue_days = models.PositiveIntegerField(default=0)
    outlet = models.ForeignKey(Outlet, on_delete=models.PROTECT)
    invoice_number = models.CharField(max_length=255 , unique=True)
    invoice_date   = models.DateField()
    amount         = models.DecimalField(max_digits=12, decimal_places=2)
    brand          = models.CharField(max_length=255)
    assigned_to    = models.ForeignKey(settings.AUTH_USER_MODEL,
                                       null=True, blank=True,
                                       on_delete=models.SET_NULL,
                                       limit_choices_to={'role':'dra'})
    status         = models.CharField(max_length=10,
                                      choices=STATUS_CHOICES,
                                      default='open')
    created_at     = models.DateTimeField(auto_now_add=True)
    cleared_at   = models.DateTimeField(null=True, blank=True)

    @property
    def remaining_amount(self):
        paid = (
            self.payments
                .aggregate(total=Sum('amount'))    # SQL SUM(payments.amount)
                .get('total')
            or Decimal('0')
        )
        return self.amount - paid

    def save(self, *args, **kwargs):
        # If we’ve just been marked “cleared” and haven’t set cleared_at yet:
        if self.status == 'cleared' and self.cleared_at is None:
            now = timezone.now()
            self.cleared_at = now
            # days between creation date and clear date
            delta = now.date() - self.created_at.date()
            self.overdue_days = delta.days

        # If still open, keep updating overdue_days on each save
        elif self.status == 'open':
            today = timezone.now().date()
            delta = today - self.created_at.date()
            self.overdue_days = delta.days

        super().save(*args, **kwargs)

    @property
    def route(self):
        return self.outlet.route

    def __str__(self):
        return f'{self.outlet} #{self.invoice_number}'



