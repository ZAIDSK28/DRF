from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum, Q
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
    STATUS_OPEN = 'open'
    STATUS_CLEARED = 'cleared'
    STATUS_CHOICES = (
        (STATUS_OPEN, 'Open'),
        (STATUS_CLEARED, 'Cleared'),
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
    )
    

    overdue_days = models.PositiveIntegerField(default=0)
    outlet = models.ForeignKey(Outlet, on_delete=models.PROTECT)
    invoice_number = models.CharField(max_length=255 , unique=True)
    invoice_date   = models.DateField()
    actual_amount  = models.DecimalField(max_digits=12, decimal_places=2)
    brand          = models.CharField(max_length=255 , default="",blank=True,)
    assigned_to    = models.ForeignKey(settings.AUTH_USER_MODEL,
                                       null=True, blank=True,
                                       on_delete=models.SET_NULL,
                                       limit_choices_to={'role':'dra'})
    status         = models.CharField(max_length=10,
                                      choices=STATUS_CHOICES,
                                      default='open')
    created_at     = models.DateTimeField(auto_now_add=True)
    cleared_at   = models.DateTimeField(null=True, blank=True)
    remaining_amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=Decimal('0.00'),
        help_text="actual_amount minus all payments"
    )


    def save(self, *args, **kwargs):
        today = timezone.localdate()
        is_new = self.pk is None

        # ——— 1) on create: just set remaining to full amount ———
        if is_new:
            # first save to get a PK
            super().save(*args, **kwargs)
            self.remaining_amount = self.actual_amount
            # also calc overdue_days for initial state
            delta = (today - self.invoice_date).days
            self.overdue_days = max(delta, 0)
            # finally write those two fields
            return Bill.objects.filter(pk=self.pk).update(
                remaining_amount=self.remaining_amount,
                overdue_days=self.overdue_days
            )

        # ——— 2) on update: recalc overdue_days and remaining_amount ———
        # fetch previous status
        prev_status = Bill.objects.only('status').get(pk=self.pk).status

        # overdue_days logic
        if self.status == self.STATUS_OPEN:
            delta = (today - self.invoice_date).days
            self.overdue_days = max(delta, 0)
        elif self.status == self.STATUS_CLEARED and prev_status != self.STATUS_CLEARED:
            delta = (today - self.invoice_date).days
            self.overdue_days = max(delta, 0)
            if not self.cleared_at:
                self.cleared_at = timezone.now()
        # else already cleared: leave overdue_days/cleared_at intact

        # initial save so we have a PK and timestamps right
        super().save(*args, **kwargs)

        # now safely aggregate payments to recalc remaining_amount
        paid_qs = self.user_payments.filter(
            Q(payment_method__in=['cash','upi']) |
            Q(payment_method__in=['cheque','electronic'], cheque_status='cleared')
        )
        paid = paid_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        new_rem = self.actual_amount - paid

        Bill.objects.filter(pk=self.pk).update(remaining_amount=new_rem)

    @property
    def route(self):
        return self.outlet.route

    def __str__(self):
        return f'{self.outlet} #{self.invoice_number}'



