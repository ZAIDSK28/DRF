from django.contrib import admin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('pk','bill', 'dra', 'payment_method', 'amount', 'created_at')
    list_filter = ('payment_method', 'dra')
    search_fields = ('bill__invoice_number', 'dra__username')
    ordering = ('-created_at',)
