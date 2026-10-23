from rest_framework.pagination import PageNumberPagination

class JobPagination(PageNumberPagination):
    #Defaults number of jobs returned per page
    page_size = 10

    #Allow clients to customize the page size
    page_size_query_param = 'page_size'

    #Prevents clients from accessing extremely lage pages.
    max_page_size = 100









