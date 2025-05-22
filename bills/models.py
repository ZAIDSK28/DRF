from django.db import models
from django.conf import settings

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

    outlet = models.ForeignKey(Outlet, on_delete=models.PROTECT)
    invoice_number = models.CharField(max_length=255)
    invoice_date   = models.DateField()
    amount         = models.DecimalField(max_digits=12, decimal_places=2)
    brand          = models.CharField(max_length=255)
    # route          = models.CharField(max_length=255)
    assigned_to    = models.ForeignKey(settings.AUTH_USER_MODEL,
                                       null=True, blank=True,
                                       on_delete=models.SET_NULL,
                                       limit_choices_to={'role':'dra'})
    status         = models.CharField(max_length=10,
                                      choices=STATUS_CHOICES,
                                      default='open')
    created_at     = models.DateTimeField(auto_now_add=True)

    @property
    def route(self):
        return self.outlet.route

    def __str__(self):
        return f'{self.outlet} #{self.invoice_number}'



