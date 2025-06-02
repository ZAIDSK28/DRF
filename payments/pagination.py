# payments/pagination.py
from rest_framework.pagination import PageNumberPagination

class PaymentPagination(PageNumberPagination):
    # Default page size if the client does not supply “limit”
    page_size = 10

    # Allow client to set page size via “?limit=…”
    page_size_query_param = 'limit'

    # Client can pick which page via “?page=…”
    page_query_param = 'page'

    # Optional: enforce a maximum page size
    max_page_size = 100
