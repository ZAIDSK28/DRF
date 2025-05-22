from rest_framework import serializers
from .models import Bill , Outlet , Route
from payments.serializers import PaymentSerializer
from users.models import User

class RouteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Route
        fields = "__all__"

class OutletSerializer(serializers.ModelSerializer):
    route = serializers.StringRelatedField()      # human-readable
    route_id = serializers.PrimaryKeyRelatedField(  # writable
        source='route',
        queryset=Route.objects.all(),
        write_only=True
    )

    class Meta:
        model  = Outlet
        fields = ("id", "name", "route", "route_id")
class BillSerializer(serializers.ModelSerializer):
    outlet = serializers.PrimaryKeyRelatedField(queryset=Outlet.objects.all())
    route  = serializers.ReadOnlyField(source="outlet.route.name")  # optional

    class Meta:
        model  = Bill
        fields = "__all__"

class BillCreateSerializer(serializers.ModelSerializer):
    route = serializers.ReadOnlyField(source='outlet.route.name')
    class Meta:
        model = Bill
        fields = (
            'outlet','invoice_number','invoice_date',
            'amount','brand','route'
        )

class BillAssignSerializer(serializers.Serializer):
    dra_id = serializers.IntegerField()

class ExcelImportSerializer(serializers.Serializer):
    file = serializers.FileField()
