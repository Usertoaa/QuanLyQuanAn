from django.urls import path
from . import views

urlpatterns = [
    path('add/', views.add_restaurant, name='add_restaurant'),

    path('', views.map_view, name='user_map'), 

    path('api/restaurants/', views.api_get_restaurants, name='api_get_restaurants'),
]