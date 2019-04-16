from django.conf.urls import url
from django.conf.urls import include


from . import views as search_view


urlpatterns = [
    url(r'^$', search_view.index, name = 'search_index'),
    url(r'^experts/$', search_view.get_search, name = 'get_search'),
]