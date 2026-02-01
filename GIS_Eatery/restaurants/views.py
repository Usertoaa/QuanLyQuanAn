from django.shortcuts import render
from django.http import JsonResponse
from .models import Restaurant
from django.core.serializers import serialize
import json

def restaurant_map(request):
    return render(request, 'restaurants/map.html')

def restaurant_data(request):
    restaurants = Restaurant.objects.all()
    data = json.loads(serialize('geojson', restaurants))
    return JsonResponse(data, safe=False)
