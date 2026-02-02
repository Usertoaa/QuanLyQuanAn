from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    
    path('', views.index, name='index'),

    path('my-admin/', views.admin_dashboard, name='admin_dashboard'),

    path('map/', views.map_view, name='map_view'),

    path('add/', views.add_restaurant, name='add_restaurant'),

    path('api/restaurants/', views.api_get_restaurants, name='api_get_restaurants'),

    path('api/book/', views.api_book_table, name='api_book_table'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)