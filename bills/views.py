import io
import pandas as pd

from rest_framework import generics, status, permissions, viewsets
from rest_framework.generics import GenericAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from django.db import transaction

from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import Bill, Route, Outlet
from .serializers import (
    BillSerializer,
    BillCreateSerializer,
    BillAssignSerializer,
    ExcelImportSerializer,
    RouteSerializer,
    OutletSerializer,
    RouteSimpleSerializer,
    OutletSimpleSerializer,
    BillSimpleSerializer,
)
from payments.models import Payment
from payments.serializers import PaymentSerializer


def export_bills(format: str):
    qs = Bill.objects.all()
    df = pd.DataFrame.from_records(qs.values(
        'pk',
        'outlet__name',
        'invoice_number',
        'invoice_date',
        'actual_amount',
        "remaining_amount",
        'status',
        'assigned_to__username',
        'overdue_days',
    ))

    if format == 'xlsx':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Bills')
        output.seek(0)
        return (
            output.getvalue(),
            'bills.xlsx',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    else:
        csv = df.to_csv(index=False)
        return csv.encode(), 'bills.csv', 'text/csv'


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_admin


class BillListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/bills/    → list all bills
    POST /api/bills/    → create a new bill
    """
    queryset = Bill.objects.all()
    permission_classes = (IsAdmin,)

    def get_serializer_class(self):
        return BillCreateSerializer if self.request.method == 'POST' else BillSerializer


class BillDetailView(generics.RetrieveUpdateAPIView):
    """
    GET    /api/bills/{pk}/    → retrieve a bill
    PUT    /api/bills/{pk}/    → update a bill
    PATCH  /api/bills/{pk}/    → partial update
    """
    queryset = Bill.objects.all()
    permission_classes = (IsAdmin,)
    serializer_class   = BillSerializer


class BillAssignView(GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class   = BillAssignSerializer

    @extend_schema(
        request   = BillAssignSerializer,
        responses = BillSerializer,
    )
    def post(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        bill_ids = ser.validated_data['bill_ids']
        dra_id   = ser.validated_data['dra_id']

        bills = Bill.objects.filter(id__in=bill_ids)
        bills.update(assigned_to_id=dra_id)

        out = BillSerializer(bills, many=True)
        return Response(out.data, status=status.HTTP_200_OK)


class BillImportView(GenericAPIView):
    serializer_class = ExcelImportSerializer
    # …

    def post(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        file = ser.validated_data['file']

        df = pd.read_excel(file)
        required = {'invoice_number','invoice_date','amount','assigned_to'}
        missing  = required - set(df.columns)
        if missing:
            return Response({'error': f'Missing columns: {missing}'}, status=status.HTTP_400_BAD_REQUEST)

        summary = {'imported': 0, 'errors': []}
        with transaction.atomic():
            for idx, row in df.iterrows():
                # … coerce types or use a DRF serializer …
                # check duplicates, then Bill.objects.create(...)
                # increment summary or collect row errors
                pass

        return Response(summary)


class ReportExportView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        request   = None,
        responses = {200: OpenApiResponse(description="CSV or XLSX file")},
    )
    def get(self, request, *args, **kwargs):
        fmt = request.query_params.get('format', 'csv')
        content, filename, content_type = export_bills(fmt)
        resp = HttpResponse(content, content_type=content_type)
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp


class RouteViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /api/routes/              → list all routes
    GET  /api/routes/{pk}/         → retrieve a single route
    GET  /api/routes/{pk}/outlets/ → list outlets on this route
    """
    queryset         = Route.objects.all().order_by('name')
    serializer_class = RouteSerializer

    @action(detail=True, methods=['get'])
    def outlets(self, request, pk=None):
        route = self.get_object()
        qs    = Outlet.objects.filter(route=route)
        page  = self.paginate_queryset(qs)
        if page is not None:
            serializer = OutletSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = OutletSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OutletViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/outlets/         → list all outlets (or filter by ?route_id=<id>)
    GET /api/outlets/{pk}/    → retrieve a single outlet
    """
    serializer_class = OutletSerializer

    def get_queryset(self):
        qs       = Outlet.objects.select_related('route').all()
        route_id = self.request.query_params.get('route_id')
        if route_id is not None:
            qs = qs.filter(route_id=route_id)
        return qs

class IsDRA(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.role == 'dra')

    
class MyAssignmentsFlatView(APIView):
    """
    GET /api/my-assignments-flat/
    returns three arrays (routes, outlets, bills) filtered to request.user
    """
    permission_classes = [IsDRA]

    def get(self, request):
        user = request.user
        routes_qs  = Route.objects.filter(outlets__bill__assigned_to=user).distinct()
        outlets_qs = Outlet.objects.filter(bill__assigned_to=user).distinct()
        bills_qs = Bill.objects.filter(
            assigned_to=user,
            status='open',
        )

        return Response({
            'routes':  RouteSimpleSerializer(routes_qs,  many=True).data,
            'outlets': OutletSimpleSerializer(outlets_qs, many=True).data,
            'bills':   BillSimpleSerializer(bills_qs,   many=True).data,
        })
