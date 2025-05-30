from rest_framework import serializers
from .models import Bill , Outlet , Route
from payments.serializers import PaymentSerializer
from users.models import User
from .models import Route, Outlet, Bill

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
    route_name  = serializers.ReadOnlyField(source="outlet.route.name")  
    route  = serializers.ReadOnlyField(source="outlet.route.id")  
    outlet_name = serializers.ReadOnlyField(
        source='outlet.name'
    )
    assigned_to_id = serializers.PrimaryKeyRelatedField(
        source='assigned_to', queryset=User.objects.all(),
    )
    assigned_to_name = serializers.CharField(
        source='assigned_to.username', read_only=True
    )
    remaining_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True )

    class Meta:
        model  = Bill
        fields = (
            "id",
            "outlet",
            "outlet_name",
            "route",
            "route_name",
            "invoice_number",
            "invoice_date",
            "actual_amount",
            "remaining_amount",
            "brand",
            "status",
            "cleared_at",
            "overdue_days",
            "assigned_to_id",
            "assigned_to_name",
        )

class BillCreateSerializer(serializers.ModelSerializer):
    route = serializers.ReadOnlyField(source='outlet.route.name')
    class Meta:
        model = Bill
        fields = (
            'outlet','invoice_number','invoice_date',
            'actual_amount','brand','route'
        )

class BillAssignSerializer(serializers.Serializer):
    bill_ids = serializers.ListField(child=serializers.IntegerField())
    dra_id   = serializers.IntegerField()


class ExcelImportSerializer(serializers.Serializer):
    file = serializers.FileField()

class RouteSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Route
        fields = ('id', 'name')


class OutletSimpleSerializer(serializers.ModelSerializer):
    route_id   = serializers.ReadOnlyField(source='route.id')
    route_name = serializers.ReadOnlyField(source='route.name')

    class Meta:
        model  = Outlet
        fields = ('id', 'name', 'route_id', 'route_name')


class BillSimpleSerializer(serializers.ModelSerializer):
    outlet_id      = serializers.ReadOnlyField(source='outlet.id')
    outlet_name    = serializers.ReadOnlyField(source='outlet.name')
    route_id       = serializers.ReadOnlyField(source='outlet.route.id')
    route_name     = serializers.ReadOnlyField(source='outlet.route.name')
    invoice_number = serializers.ReadOnlyField()
    invoice_date   = serializers.ReadOnlyField()

    class Meta:
        model  = Bill
        fields = (
            'id',
            'invoice_number',
            'invoice_date',
            'actual_amount',
            'brand',
            'status',
            'overdue_days',
            'route_id',
            'route_name',
            'outlet_id',
            'outlet_name',
        )
