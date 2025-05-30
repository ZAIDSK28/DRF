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
        paid = (self.payments.aggregate(total=Sum('amount'))['total'] or 0)
        return self.amount - paid

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        today = timezone.now().date()
        # always compute overdue_days from creation
        self.overdue_days = (today - self.created_at.date()).days

        if self.status == 'cleared' and not self.cleared_at:
            self.cleared_at = timezone.now()

        super().save(update_fields=['overdue_days', 'cleared_at'] if self.cleared_at else ['overdue_days'])


    @property
    def route(self):
        return self.outlet.route

    def __str__(self):
        return f'{self.outlet} #{self.invoice_number}'



