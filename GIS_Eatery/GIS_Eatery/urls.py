from django.urls import include
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path('restaurants/', include('restaurants.urls')),
]
