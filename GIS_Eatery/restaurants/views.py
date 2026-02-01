from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.core.serializers import serialize
from django.contrib.gis.geos import Point
from .models import Restaurant, Table, Reservation
import json

# --- 1. Chức năng Thêm Quán Ăn (Admin) ---
def add_restaurant(request):
    if request.method == "POST":
        name = request.POST.get('name')
        address = request.POST.get('address')
        try:
            lat = float(request.POST.get('lat'))
            lng = float(request.POST.get('lng'))
            pnt = Point(lng, lat, srid=4326)
            
            Restaurant.objects.create(name=name, address=address, location=pnt)
            return redirect('add_restaurant')
        except (ValueError, TypeError):
            return render(request, 'restaurants/add_restaurant.html', {'error': 'Vui lòng chọn vị trí trên bản đồ!'})
            
    return render(request, 'restaurants/add_restaurant.html')


# --- 2. Chức năng Hiển thị Bản đồ (User) ---
def map_view(request):
    """Trả về giao diện bản đồ cho người dùng"""
    return render(request, 'restaurants/user_map.html')


# --- 3. API Trả về dữ liệu GeoJSON ---
def api_get_restaurants(request):
    """API trả về dữ liệu GeoJSON của toàn bộ quán ăn"""
    restaurants = Restaurant.objects.all()
    # Serialize dữ liệu sang GeoJSON để Leaflet có thể đọc được
    data = serialize('geojson', restaurants, geometry_field='location', fields=('name', 'address'))
    return JsonResponse(json.loads(data), safe=False)