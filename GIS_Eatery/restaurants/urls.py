from django.urls import path
from . import views

urlpatterns = [
    path('map/', views.restaurant_map, name='restaurant_map'),
    path('api/data/', views.restaurant_data, name='restaurant_data'),
    path('my-admin/', views.admin_dashboard, name='admin_dashboard'),
    path('my-admin/add/', views.add_restaurant, name='add_restaurant'),
]