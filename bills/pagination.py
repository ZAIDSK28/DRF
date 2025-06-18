# bills/pagination.py

from rest_framework.pagination import PageNumberPagination

class BillPagination(PageNumberPagination):
    """
    A simple PageNumberPagination for “my bills” (and/or any Bill‐related lists).
    Frontend can specify ?page=<n>&limit=<m>.
    """
    page_size = 10                        # default if ?limit is omitted
    page_size_query_param = 'limit'       # ?limit=<m> overrides page_size
    page_query_param = 'page'             # ?page=<n> picks the page
    max_page_size = 100                   # never allow more than 100 at once
