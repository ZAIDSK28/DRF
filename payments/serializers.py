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

    def validate_amount(self, value):
        """
        1) Look up the Bill by bill_id (passed as a URL kwarg).
        2) If bill.remaining_amount == 0, reject immediately.
        3) If value > bill.remaining_amount, reject as an over‐payment.
        Otherwise, return value.
        """
        view = self.context.get("view")
        bill_id = view.kwargs.get("bill_id")
        bill = get_object_or_404(Bill, pk=bill_id)

        # 1) Bill already fully paid?
        if bill.remaining_amount <= 0:
            raise serializers.ValidationError(
                "This bill is already fully paid (remaining amount is 0)."
            )

        # 2) Over‐payment?
        if value > bill.remaining_amount:
            raise serializers.ValidationError(
                f"Cannot pay {value}. Remaining amount is only {bill.remaining_amount}."
            )

        return value

class PaymentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            'payment_method','amount','transaction_photo',
            'cheque_type','cheque_number','cheque_date'
        )

