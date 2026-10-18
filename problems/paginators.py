from rest_framework.pagination import PageNumberPagination

class ProblemPagination(PageNumberPagination):
    max_page_size = 100
    page_size = 20

class CommentPagination(PageNumberPagination):
    max_page_size = 100
    page_size = 20

class HistoryPagination(PageNumberPagination):
    max_page_size = 100
    max_size = 20