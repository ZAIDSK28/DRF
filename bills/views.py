from datetime import timezone
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

from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import Bill, Route, Outlet
from bills.models import Bill
from payments.models import Payment
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


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_admin


class BillListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/bills/    → list all bills (or filter by ?invoice_number=…)
    POST /api/bills/    → create a new bill
    """
    serializer_class = BillSerializer  # overridden in get_serializer_class()
    permission_classes = (IsAdmin,)
    pagination_class = BillPagination

    def get_queryset(self):
        """
        Base queryset, optionally filtered by ?invoice_number=<value>.
        Always ordered by -created_at.
        """
        qs = Bill.objects.all().order_by('-created_at')
        inv = self.request.query_params.get('invoice_number')
        if inv:
            # Filter any bill whose invoice_number contains the supplied string
            qs = qs.filter(invoice_number__icontains=inv)
        return qs

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
            OpenApiParameter(
                name='invoice_number',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='(Optional) Filter bills whose invoice_number contains this string.',
                required=False,
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        """
        Override `list()` so that:
        1) If neither `page` nor `limit` is present, return all bills (filtered by invoice_number if given).
        2) Otherwise, attempt to paginate using ?page & ?limit, falling back to defaults on invalid values.
        """
        # 1) Grab the filtered queryset (accounts for invoice_number)
        base_qs = self.filter_queryset(self.get_queryset())

        # 2) Try to paginate normally (DRF will read ?page & ?limit)
        try:
            page_qs = self.paginate_queryset(base_qs)
        except Exception:
            # On any pagination error (e.g. invalid page/limit), strip both params and retry
            mutable_qs = request.query_params.copy()
            mutable_qs.pop('page', None)
            mutable_qs.pop('limit', None)
            request._request.GET = mutable_qs
            page_qs = self.paginate_queryset(self.filter_queryset(self.get_queryset()))

        # 3) If neither page nor limit was in the query, return the full (filtered) set
        if 'page' not in request.query_params and 'limit' not in request.query_params:
            serializer = self.get_serializer(base_qs, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # 4) Otherwise, DRF pagination applies (either valid or after fallback). If paginate_queryset()
        #    returned a page object, return the paginated response; else, return all.
        if page_qs is not None:
            serializer = self.get_serializer(page_qs, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(base_qs, many=True)
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
    """
    POST /api/payments/import/

    Expects an Excel file (.xlsx) with columns matching your exports:
      - "Bill ID"           (optional; we use "Invoice Number" to find the Bill)
      - "Brand"             (ignored for import)
      - "Invoice Date"      (ignored for import)
      - "Route Name"        (ignored for import)
      - "Invoice Number"    (Required: used to look up the Bill)
      - "Outlet Name"       (ignored for import)
      - "Payment Amount"    (Required: numeric)
      - "Username"          (Required: matches dra__username, i.e. the paying user)
      - "Overdue Days"      (ignored for import)
      - "Cheque #"          (Optional: if your Payment model has a cheque_number field)
      - "Cheque Date"       (Optional: if your Payment model has a cheque_date field)
      - "Payment Date"      (Required: when the payment was made)
    Additional columns (if present) are ignored. Each row is processed independently;
    errors are collected in the "errors" list, and successful rows increment "imported".

    Returns a JSON response of the form:
      {
        "imported": <count_of_successful_rows>,
        "errors": [
          {"row": <excel_row_number>, "error": "<message>"},
          ...
        ]
      }
    """

    serializer_class = ExcelImportSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        # 1) Validate that a file was uploaded
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        excel_file = ser.validated_data["file"]

        # 2) Load into a pandas DataFrame
        try:
            df = pd.read_excel(excel_file)
        except Exception as e:
            return Response(
                {"detail": f"Error reading Excel file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3) Normalize column names by stripping whitespace
        df.columns = [c.strip() for c in df.columns]

        # 4) The import sheet must at least contain these column headers:
        required = {
            "Invoice Number",
            "Payment Amount",
            "Username",
            "Payment Date",
        }
        missing = required - set(df.columns)
        if missing:
            return Response(
                {"error": f"Missing required columns: {sorted(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        summary = {"imported": 0, "errors": []}

        for idx, row in df.iterrows():
            row_num = idx + 2  # Excel row = index + header row

            # 5a) Invoice Number → lookup Bill
            raw_inv = row.get("Invoice Number")
            if pd.isna(raw_inv) or str(raw_inv).strip() == "":
                summary["errors"].append(
                    {"row": row_num, "error": "Invoice Number is blank"}
                )
                continue
            invoice_number = str(raw_inv).strip()
            bill = Bill.objects.filter(invoice_number=invoice_number).first()
            if not bill:
                summary["errors"].append(
                    {"row": row_num, "error": f"Bill with Invoice Number '{invoice_number}' not found"}
                )
                continue

            # 5b) Payment Amount → numeric
            raw_amt = row.get("Payment Amount")
            if pd.isna(raw_amt):
                summary["errors"].append(
                    {"row": row_num, "error": "Payment Amount is blank"}
                )
                continue
            try:
                amt_str = str(raw_amt).replace(",", "").replace("$", "")
                payment_amount = float(amt_str)
            except (ValueError, TypeError):
                summary["errors"].append(
                    {"row": row_num, "error": f"Invalid Payment Amount: '{raw_amt}'"}
                )
                continue

            # 5c) Username → lookup User (dra)
            raw_user = row.get("Username")
            if pd.isna(raw_user) or str(raw_user).strip() == "":
                summary["errors"].append(
                    {"row": row_num, "error": "Username is blank"}
                )
                continue
            identifier = str(raw_user).strip()
            dra = (
                User.objects.filter(username=identifier).first()
                or User.objects.filter(email=identifier).first()
            )
            if not dra:
                summary["errors"].append(
                    {"row": row_num, "error": f"User '{identifier}' not found"}
                )
                continue

            # 5d) Payment Date → parse to a date
            raw_date = row.get("Payment Date")
            if pd.isna(raw_date):
                summary["errors"].append(
                    {"row": row_num, "error": "Payment Date is blank"}
                )
                continue

            if isinstance(raw_date, pd.Timestamp):
                payment_date = raw_date.to_pydatetime()
            else:
                # Try ISO‐format first
                parsed = parse_date(str(raw_date))
                if parsed:
                    # convert date → datetime at midnight
                    payment_date = timezone.datetime(
                        parsed.year, parsed.month, parsed.day, tzinfo=timezone.get_current_timezone()
                    )
                else:
                    # Fallback: let pandas parse
                    try:
                        payment_date = pd.to_datetime(str(raw_date))
                    except Exception:
                        payment_date = None

            if not payment_date:
                summary["errors"].append(
                    {"row": row_num, "error": f"Invalid Payment Date: '{raw_date}'"}
                )
                continue

            # 5e) Optional: Cheque # and Cheque Date if your Payment model expects them
            cheque_number = None
            if "Cheque #" in df.columns:
                raw_chq = row.get("Cheque #")
                if not pd.isna(raw_chq):
                    cheque_number = str(raw_chq).strip()

            cheque_date = None
            if "Cheque Date" in df.columns:
                raw_chq_date = row.get("Cheque Date")
                if not pd.isna(raw_chq_date):
                    if isinstance(raw_chq_date, pd.Timestamp):
                        cheque_date = raw_chq_date.to_pydatetime().date()
                    else:
                        parsed_chq = parse_date(str(raw_chq_date))
                        if not parsed_chq:
                            # fallback
                            try:
                                cheque_date = pd.to_datetime(str(raw_chq_date)).date()
                            except:
                                cheque_date = None
                        else:
                            cheque_date = parsed_chq

            # 5f) Finally, create the Payment instance
            try:
                Payment.objects.create(
                    bill=bill,
                    dra=dra,
                    amount=payment_amount,
                    created_at=payment_date,
                    cheque_number=cheque_number,
                    cheque_date=cheque_date,
                    payment_method="Imported",  # or default logic
                )
                summary["imported"] += 1
            except Exception as e:
                summary["errors"].append(
                    {"row": row_num, "error": f"Database error: {str(e)}"}
                )
                continue

        return Response(summary, status=status.HTTP_200_OK)


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
    

def export_bills_xlsx(start_date=None, end_date=None):
    """
    Export bills as an XLSX file, with columns in this exact order:
      1) Bill ID
      2) Brand
      3) Invoice Date
      4) Route Name
      5) Invoice Number
      6) Outlet Name
      7) Remaining Amount
      8) Overdue Days
      9) Actual Amount

    Only bills whose invoice_date is between start_date and end_date are included.
    If start_date or end_date is None, that bound is ignored.

    Overdue Days is computed as:
      max( (today – invoice_date).days , 0 )

    Returns: (content_bytes, filename, content_type)
    """
    bills_qs = Bill.objects.select_related("outlet__route").all()
    if start_date:
        bills_qs = bills_qs.filter(invoice_date__gte=start_date)
    if end_date:
        bills_qs = bills_qs.filter(invoice_date__lte=end_date)

    raw_values = bills_qs.values(
        "pk",
        "brand",
        "invoice_date",
        "invoice_number",
        "remaining_amount",
        "actual_amount",
        "outlet__name",
        "outlet__route__name",
    )

    bills_df = pd.DataFrame.from_records(raw_values)

    if bills_df.empty:
        bills_df = pd.DataFrame(
            columns=[
                "pk",
                "brand",
                "invoice_date",
                "invoice_number",
                "remaining_amount",
                "actual_amount",
                "outlet__name",
                "outlet__route__name",
            ]
        )

   
    today = timezone.localdate()
    def compute_overdue(row):
        inv_date = row["invoice_date"]
        if pd.isna(inv_date):
            return 0
        inv = inv_date.to_pydatetime().date() if isinstance(inv_date, pd.Timestamp) else inv_date
        delta = (today - inv).days
        return max(delta, 0)

    bills_df["Overdue Days"] = bills_df.apply(compute_overdue, axis=1)

    bills_df = bills_df.rename(
        columns={
            "pk": "Bill ID",
            "brand": "Brand",
            "invoice_date": "Invoice Date",
            "outlet__route__name": "Route Name",
            "invoice_number": "Invoice Number",
            "outlet__name": "Outlet Name",
            "remaining_amount": "Outstanding Amount",
            "actual_amount": "Invoice Bill Amount",
        }
    )

    ordered_columns = [
        "Bill ID",
        "Brand",
        "Invoice Date",
        "Route Name",
        "Invoice Number",
        "Outlet Name",
        "Outstanding Amount",
        "Overdue Days",
        "Invoice Bill Amount",
    ]
    bills_df = bills_df[ordered_columns]

    # 8) Strip timezone info from “Invoice Date” if present
    if "Invoice Date" in bills_df.columns and pd.api.types.is_datetime64tz_dtype(bills_df["Invoice Date"].dtype):
        bills_df["Invoice Date"] = bills_df["Invoice Date"].dt.tz_convert(None)

    # 9) Build a filename based on the date window
    start_str = start_date.isoformat() if start_date else "all"
    end_str = end_date.isoformat() if end_date else "all"
    filename = f"bills_{start_str}_to_{end_str}.xlsx"

    # 10) Write to an in‐memory XLSX file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        bills_df.to_excel(writer, index=False, sheet_name="Bills")
    content = output.getvalue()
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return content, filename, content_type



def export_payments_xlsx(start_date=None, end_date=None):
    """
    Export payments as an XLSX file, with columns in this exact order:
      1) Bill ID
      2) Brand
      3) Invoice Date
      4) Route Name
      5) Invoice Number
      6) Outlet Name
      7) Payment Amount        ← replaces “Remaining Amount”
      8) Dra Username          ← replaces “Actual Amount”
      9) Overdue Days

    Only payments whose created_at date is between start_date and end_date are included.
    Overdue Days is computed from the *bill*’s invoice_date as:
        max((today – invoice_date).days, 0)

    Returns: (content_bytes, filename, content_type)
    """

    payments_qs = Payment.objects.select_related("bill__outlet__route", "dra").all()
    if start_date:
        payments_qs = payments_qs.filter(created_at__date__gte=start_date)
    if end_date:
        payments_qs = payments_qs.filter(created_at__date__lte=end_date)

   
    raw_values = payments_qs.values(
        "bill__pk",
        "bill__brand",
        "bill__invoice_date",
        "bill__outlet__route__name",
        "bill__invoice_number",
        "bill__outlet__name",
        "amount",
        "dra__username",
    )

    payments_df = pd.DataFrame.from_records(raw_values)

    if payments_df.empty:
        payments_df = pd.DataFrame(
            columns=[
                "bill__pk",
                "bill__brand",
                "bill__invoice_date",
                "bill__outlet__route__name",
                "bill__invoice_number",
                "bill__outlet__name",
                "amount",
                "dra__username",
            ]
        )

    today = timezone.localdate()

    def compute_overdue(row):
        inv_date = row["bill__invoice_date"]
        if pd.isna(inv_date):
            return 0
        inv = inv_date.to_pydatetime().date() if isinstance(inv_date, pd.Timestamp) else inv_date
        delta = (today - inv).days
        return max(delta, 0)

    payments_df["Overdue Days"] = payments_df.apply(compute_overdue, axis=1)

    payments_df = payments_df.rename(
        columns={
            "bill__pk":                "Bill ID",
            "bill__brand":             "Brand",
            "bill__invoice_date":      "Invoice Date",
            "bill__outlet__route__name": "Route Name",
            "bill__invoice_number":    "Invoice Number",
            "bill__outlet__name":      "Outlet Name",
            "amount":                  "Payment Amount",
            "dra__username":           "Username",
        }
    )

    ordered_columns = [
        "Bill ID",
        "Brand",
        "Invoice Date",
        "Route Name",
        "Invoice Number",
        "Outlet Name",
        "Payment Amount",
        "Username",
        "Overdue Days",
    ]
    payments_df = payments_df[ordered_columns]

    # 7) Drop any timezone info from “Invoice Date” if present
    if "Invoice Date" in payments_df.columns and pd.api.types.is_datetime64tz_dtype(payments_df["Invoice Date"].dtype):
        payments_df["Invoice Date"] = payments_df["Invoice Date"].dt.tz_convert(None)

    # 8) Build the output filename based on the date window
    start_str = start_date.isoformat() if start_date else "all"
    end_str = end_date.isoformat() if end_date else "all"
    filename = f"payments_{start_str}_to_{end_str}.xlsx"

    # 9) Write DataFrame to an in‐memory XLSX file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        payments_df.to_excel(writer, index=False, sheet_name="Payments")
    content = output.getvalue()
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return content, filename, content_type


class BillExportView(APIView):
    """
    GET /api/bills/export-bills/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
      → returns a single XLSX file containing only bills in that date range.
    """
    permission_classes = (IsAuthenticated,)  # or (IsAuthenticated,) if you want auth

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="start_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="(Optional) YYYY-MM-DD. Filter bills with invoice_date ≥ start_date.",
                required=False,
            ),
            OpenApiParameter(
                name="end_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="(Optional) YYYY-MM-DD. Filter bills with invoice_date ≤ end_date.",
                required=False,
            ),
        ],
        responses={
            200: OpenApiTypes.BINARY,
            400: OpenApiResponse(description="Invalid date format"),
        },
    )
    def get(self, request, *args, **kwargs):
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")

        start_date = parse_date(raw_start) if raw_start else None
        end_date = parse_date(raw_end) if raw_end else None

        if raw_start and not start_date:
            return Response(
                {"detail": "Invalid start_date. Must be YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if raw_end and not end_date:
            return Response(
                {"detail": "Invalid end_date. Must be YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content, filename, content_type = export_bills_xlsx(start_date, end_date)
        resp = HttpResponse(content, content_type=content_type)
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp


class PaymentExportView(APIView):
    """
    GET /api/bills/export-payments/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
      → returns a single XLSX file containing only payments in that date range.
    """
    permission_classes = (IsAuthenticated,)  # or (IsAuthenticated,) if you want auth

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="start_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="(Optional) YYYY-MM-DD. Filter payments with created_at ≥ start_date.",
                required=False,
            ),
            OpenApiParameter(
                name="end_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="(Optional) YYYY-MM-DD. Filter payments with created_at ≤ end_date.",
                required=False,
            ),
        ],
        responses={
            200: OpenApiTypes.BINARY,
            400: OpenApiResponse(description="Invalid date format"),
        },
    )
    def get(self, request, *args, **kwargs):
        raw_start = request.query_params.get("start_date")
        raw_end = request.query_params.get("end_date")

        start_date = parse_date(raw_start) if raw_start else None
        end_date = parse_date(raw_end) if raw_end else None

        if raw_start and not start_date:
            return Response(
                {"detail": "Invalid start_date. Must be YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if raw_end and not end_date:
            return Response(
                {"detail": "Invalid end_date. Must be YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content, filename, content_type = export_payments_xlsx(start_date, end_date)
        resp = HttpResponse(content, content_type=content_type)
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp