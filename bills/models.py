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
        # Detect insert vs update
        is_new = self.pk is None

        # First let Django populate created_at, etc.
        super().save(*args, **kwargs)

        # Now that created_at exists, compute overdue_days / cleared_at
        if is_new:
            # On first save, if status=='cleared', stamp cleared_at
            if self.status == 'cleared' and self.cleared_at is None:
                now = timezone.now()
                self.cleared_at   = now
                self.overdue_days = (now.date() - self.created_at.date()).days
                super().save(update_fields=['cleared_at', 'overdue_days'])
        else:
            # On subsequent saves, keep overdue_days up to date if still open
            if self.status == 'open':
                self.overdue_days = (timezone.now().date() - self.created_at.date()).days
                super().save(update_fields=['overdue_days'])

    @property
    def route(self):
        return self.outlet.route

    def __str__(self):
        return f'{self.outlet} #{self.invoice_number}'



