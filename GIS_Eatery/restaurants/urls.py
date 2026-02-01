from django.urls import path
from . import views

urlpatterns = [
    path('map/', views.restaurant_map, name='restaurant_map'),
    path('api/data/', views.restaurant_data, name='restaurant_data'),
]