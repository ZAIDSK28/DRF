from rest_framework import serializers
from .models import Payment

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
