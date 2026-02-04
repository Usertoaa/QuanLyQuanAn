from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Trang chính
    path('', views.index, name='index'),

    path('api/restaurants/', views.api_get_restaurants, name='api_get_restaurants'),

    path('api/book/', views.api_book_table, name='api_book_table'),

    # Admin URLs
    path('admin/', views.admin_dashboard, name='admin_dashboard'),

    path('my-admin/restaurants/', views.admin_restaurant_list, name='admin_restaurant_list'),
    # Quan Ly Quan An
    path('my-admin/restaurants/', views.admin_restaurant_list, name='admin_restaurant_list'),
    path('my-admin/restaurants/add/', views.admin_restaurant_form, name='admin_restaurant_add'),
    path('my-admin/restaurants/edit/<int:pk>/', views.admin_restaurant_form, name='admin_restaurant_edit'),
    path('my-admin/restaurants/delete/<int:pk>/', views.admin_restaurant_delete, name='admin_restaurant_delete'),
    # Quan Ly Dat Ban
    path('my-admin/bookings/', views.admin_reservations, name='admin_reservations'),

    path('restaurant/<int:pk>/', views.restaurant_detail, name='restaurant_detail'),
    
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)