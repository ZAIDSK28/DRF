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
from django.utils.dateparse import parse_date


from drf_spectacular.utils import extend_schema, OpenApiResponse
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

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
from bills.pagination import BillPagination

def export_bills(fmt: str, start_date=None, end_date=None):
    """
    Build a DataFrame from Bill objects, optionally filtered by:
      - invoice_date >= start_date
      - invoice_date <= end_date
    Then render to CSV or XLSX.
    """
    qs = Bill.objects.all()

    # NOTE: parse_date() turns a “YYYY-MM-DD” string into a date object.
    if start_date:
        # Only include bills whose invoice_date is on/after start_date:
        qs = qs.filter(invoice_date__gte=start_date)

    if end_date:
        # Only include bills whose invoice_date is on/before end_date:
        qs = qs.filter(invoice_date__lte=end_date)

    df = pd.DataFrame.from_records(qs.values(
        'pk',
        'outlet__name',
        'invoice_number',
        'invoice_date',
        'actual_amount',
        'remaining_amount',
        'status',
        'assigned_to__username',
        'overdue_days',
    ))

    if fmt == 'xlsx':
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
    queryset = Bill.objects.all().order_by('-created_at')
    permission_classes = (IsAdmin,)
    pagination_class   = BillPagination


    def get_serializer_class(self):
        return BillCreateSerializer if self.request.method == 'POST' else BillSerializer
    
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='page',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Page number (1-based). Falls back to 1 if invalid.',
                required=False,
                default=1
            ),
            OpenApiParameter(
                name='limit',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Items per page. Falls back to default if invalid.',
                required=False,
                default=10
            ),
        ]
    )


    def list(self, request, *args, **kwargs):
        """
        Override `list()` so that if `page` or `limit` is missing/invalid, we
        fall back to page=1 and the default page_size defined in BillPagination.
        """
        # 1) Grab the base queryset
        queryset = self.filter_queryset(self.get_queryset())

        # 2) Try to paginate normally (DRF will read ?page & ?limit)
        try:
            page = self.paginate_queryset(queryset)
        except Exception:
            # If any pagination error occurs (e.g. invalid int in page/limit),
            # remove both params and re-run with defaults.
            mutable_qs = request.query_params.copy()
            mutable_qs.pop('page', None)
            mutable_qs.pop('limit', None)
            request._request.GET = mutable_qs  # assign back to the underlying Django GET dict

            page = self.paginate_queryset(queryset)

        # 3) If pagination applied, return paginated response
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # 4) If, for some reason, pagination still isn’t applied, return all bills
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    



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
        parameters=[
            OpenApiParameter(
                name='format',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Choose "csv" (default) or "xlsx".',
                required=False,
                default='csv'
            ),
            OpenApiParameter(
                name='start_date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='(Optional) YYYY-MM-DD. Export only bills with invoice_date ≥ start_date.',
                required=False
            ),
            OpenApiParameter(
                name='end_date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='(Optional) YYYY-MM-DD. Export only bills with invoice_date ≤ end_date.',
                required=False
            ),
        ],
        responses={200: OpenApiResponse(description="Download CSV or XLSX")},
    )
    def get(self, request, *args, **kwargs):
        # 1) Read format (csv/xlsx); default to "csv"
        fmt = request.query_params.get('format', 'csv').lower()
        if fmt not in ('csv', 'xlsx'):
            return Response(
                {"detail": 'Invalid format. Must be "csv" or "xlsx".'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2) Read & parse start_date/end_date
        raw_start = request.query_params.get('start_date')
        raw_end   = request.query_params.get('end_date')

        start_date = None
        end_date = None

        if raw_start:
            # parse_date("YYYY-MM-DD") → datetime.date or None if invalid
            parsed = parse_date(raw_start)
            if not parsed:
                return Response(
                    {"detail": 'Invalid start_date. Must be in YYYY-MM-DD format.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            start_date = parsed

        if raw_end:
            parsed = parse_date(raw_end)
            if not parsed:
                return Response(
                    {"detail": 'Invalid end_date. Must be in YYYY-MM-DD format.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            end_date = parsed

        # 3) Call export_bills with those filters
        content, filename, content_type = export_bills(fmt, start_date, end_date)

        # 4) Build the HTTP response for file download
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
    GET /api/my-assignments-flat/?page=<n>&limit=<m>
    Returns three arrays (routes, outlets, bills) for the logged-in user,
    but ONLY paginates the 'bills' array.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request, format=None):
        user = request.user

        # ─── 1) Grab all open bills assigned to this user ──────────────────────
        bills_qs = (
            Bill.objects
                .filter(assigned_to=user, status='open')
                .select_related('outlet', 'outlet__route')
                .order_by('-created_at')
        )

        # ─── 2) Grab all outlets that have at least one bill assigned to user ──
        outlets_qs = Outlet.objects.filter(
            bill__assigned_to=user
        ).distinct()

        # ─── 3) Grab all routes that have at least one such outlet ────────────
        routes_qs = Route.objects.filter(
            outlets__bill__assigned_to=user
        ).distinct()

        # ─── 4) Read pagination parameters ────────────────────────────────────
        try:
            limit = int(request.query_params.get('limit', 10))
            if limit <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"detail": "Invalid ‘limit’ parameter. Must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            page = int(request.query_params.get('page', 1))
            if page <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"detail": "Invalid ‘page’ parameter. Must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ─── 5) Compute total, slice bills_qs, and serialize ────────────────
        total_bills = bills_qs.count()
        start_index = (page - 1) * limit
        end_index   = start_index + limit

        # If the requested page is beyond the number of bills, we’ll return an empty list.
        bills_page_qs = bills_qs[start_index:end_index]
        serialized_bills = BillSimpleSerializer(bills_page_qs, many=True).data

        # Compute total_pages via ceiling division
        total_pages = (total_bills + limit - 1) // limit if total_bills > 0 else 0

        # ─── 6) Serialize routes & outlets (no pagination on these) ─────────
        serialized_routes  = RouteSimpleSerializer(routes_qs,  many=True).data
        serialized_outlets = OutletSimpleSerializer(outlets_qs, many=True).data

        # ─── 7) Return the combined payload ──────────────────────────────────
        return Response({
            "routes":  serialized_routes,
            "outlets": serialized_outlets,
            "bills":   serialized_bills,
            "pagination": {
                "limit":        limit,
                "page":         page,
                "total_items":  total_bills,
                "total_pages":  total_pages,
            }
        })