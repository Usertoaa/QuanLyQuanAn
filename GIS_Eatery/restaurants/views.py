from django.shortcuts import redirect, render
from django.http import JsonResponse
from .models import  Restaurant
from django.core.serializers import serialize
import json
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D

def admin_dashboard(request):
    restaurants = Restaurant.objects.all().order_by('-created_at')
    return render(request, 'restaurants/admin_dashboard.html', {'restaurants': restaurants})

def add_restaurant(request):
    if request.method == "POST":
        name = request.POST.get('name')
        address = request.POST.get('address')
        lat = float(request.POST.get('lat'))
        lng = float(request.POST.get('lng'))
        
        # Tạo đối tượng Point từ tọa độ trên bản đồ
        pnt = Point(lng, lat)
        
        Restaurant.objects.create(name=name, address=address, location=pnt)
        return redirect('admin_dashboard')
    return render(request, 'restaurants/add_restaurant.html')

def restaurant_map(request):
    return render(request, 'restaurants/map.html')

def restaurant_data(request):
    restaurants = Restaurant.objects.all()
    data = json.loads(serialize('geojson', restaurants))
    return JsonResponse(data, safe=False)

