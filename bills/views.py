import io
import pandas as pd
from rest_framework import generics, status, permissions , viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from django.utils import timezone
from django.core.mail import EmailMessage
from django.conf import settings
from bills.serializers import RouteSerializer, OutletSerializer
from .models import Bill , Route, Outlet
from .serializers import (
    RouteSerializer, OutletSerializer,
    BillSerializer, BillCreateSerializer,
    BillAssignSerializer, ExcelImportSerializer
)
from payments.models import Payment
from payments.serializers import PaymentSerializer
from rest_framework.decorators import action


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_admin

# 3 & 4. List & Create
class BillListCreateView(generics.ListCreateAPIView):
    queryset = Bill.objects.all()
    permission_classes = (IsAdmin,)
    def get_serializer_class(self):
        return BillCreateSerializer if self.request.method == 'POST' else BillSerializer

# 5 & 6. Retrieve & Update
class BillDetailView(generics.RetrieveUpdateAPIView):
    queryset = Bill.objects.all()
    permission_classes = (IsAdmin,)
    serializer_class = BillSerializer

# 7. Assign to DRA
class BillAssignView(APIView):
    permission_classes = (IsAdmin,)
    def post(self, request, bill_id):
        bill = generics.get_object_or_404(Bill, pk=bill_id)
        ser = BillAssignSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from users.models import User
        dra = generics.get_object_or_404(User, pk=ser.validated_data['dra_id'], role='dra')
        bill.assigned_to = dra
        bill.save()
        return Response(BillSerializer(bill).data)

# 8. Excel import
class BillImportView(APIView):
    permission_classes = (IsAdmin,)
    def post(self, request):
        ser = ExcelImportSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        df = pd.read_excel(request.FILES['file'])
        created = 0
        errors = []
        for idx,row in df.iterrows():
            try:
                route_obj, _  = Route.objects.get_or_create(name=row["route"])
                outlet_obj, _ = Outlet.objects.get_or_create(name=row["outlet_name"],
                                             route=route_obj)
                Bill.objects.create(
                    outlet=outlet_obj,
                    outlet_name=row['outlet_name'],
                    invoice_number=row['invoice_number'],
                    invoice_date=row['invoice_date'],
                    amount=row['amount'],
                    brand=row['brand'],
                    route=row['route']
                )
                created += 1
            except Exception as e:
                errors.append({'row': idx+2, 'error': str(e)})
        return Response({'created': created, 'errors': errors})

# 14. Manual Excel export
class ReportExportView(APIView):
    permission_classes = (IsAdmin,)

    def get(self, request):
        sd = request.query_params.get('start_date')
        ed = request.query_params.get('end_date', sd)
        if not sd:
            return Response({'detail':'start_date required'}, status=status.HTTP_400_BAD_REQUEST)

        start = timezone.datetime.fromisoformat(sd).date()
        end = timezone.datetime.fromisoformat(ed).date()

        # Bills
        bills = Bill.objects.filter(created_at__date__range=(start,end)).values()
        df_bills = pd.DataFrame(list(bills))

        # Payments
        pays = Payment.objects.filter(created_at__date__range=(start,end)).values()
        df_pays = pd.DataFrame(list(pays))

        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            df_bills.to_excel(writer, sheet_name='AdminEntries', index=False)
            df_pays.to_excel(writer, sheet_name='DRAEntries', index=False)
        out.seek(0)

        resp = Response(
            out.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"report_{sd}_{ed}.xlsx"
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp
class RouteViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /api/routes/             → list all routes
    GET  /api/routes/{pk}/        → retrieve a single route
    GET  /api/routes/{pk}/outlets/→ list outlets on this route
    """
    queryset = Route.objects.all().order_by('name')
    serializer_class = RouteSerializer

    @action(detail=True, methods=['get'])
    def outlets(self, request, pk=None):
        route = self.get_object()
        qs = Outlet.objects.filter(route=route)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = OutletSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = OutletSerializer(qs, many=True)
        return Response(serializer.data)


class OutletViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/outlets/         → list all outlets (or filter by ?route_id=<id>)
    GET /api/outlets/{pk}/    → retrieve a single outlet
    """
    serializer_class = OutletSerializer

    def get_queryset(self):
        qs = Outlet.objects.select_related('route').all()
        route_id = self.request.query_params.get('route_id')
        if route_id is not None:
            qs = qs.filter(route_id=route_id)
        return qs