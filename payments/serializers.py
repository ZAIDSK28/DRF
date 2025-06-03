from rest_framework import serializers
from django.shortcuts import get_object_or_404
from .models import Payment
from bills.models import Bill

class PaymentSerializer(serializers.ModelSerializer):
    route_id        = serializers.ReadOnlyField(source='bill.outlet.route.id')
    route_name      = serializers.ReadOnlyField(source='bill.outlet.route.name')
    outlet_id       = serializers.ReadOnlyField(source='bill.outlet.id')
    outlet_name     = serializers.ReadOnlyField(source='bill.outlet.name')
    invoice_number  = serializers.ReadOnlyField(source='bill.invoice_number')
    invoice_date    = serializers.ReadOnlyField(source='bill.invoice_date')
    class Meta:
        model = Payment
        fields = (
            'id',
            'bill',
            'route_id',
            'route_name',
            'outlet_id',
            'outlet_name',
            'invoice_number',
            'invoice_date',
            'payment_method',
            'amount',
            'transaction_number',
            'cheque_type',
            'cheque_number',
            'cheque_date',
            'created_at',
        )
        read_only_fields = ('dra', 'created_at')
        read_only_fields = ('dra','created_at')

class PaymentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            'payment_method','amount','transaction_photo',
            'cheque_type','cheque_number','cheque_date'
        )

    def validate_amount(self, value):
        """
        Ensure that the payment amount (value) does not exceed the Bill’s remaining_amount.
        The view must have passed 'bill_id' as part of kwargs, so we can look up the Bill.
        """
        view = self.context.get("view")
        bill_id = view.kwargs.get("bill_id")
        bill = get_object_or_404(Bill, pk=bill_id)

        if value > bill.remaining_amount:
            raise serializers.ValidationError(
                f"Payment amount cannot exceed remaining amount ({bill.remaining_amount})."
            )
        return value
