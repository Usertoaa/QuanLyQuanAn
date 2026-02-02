from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.core.serializers import serialize
from django.contrib.gis.geos import Point
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime 
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
    data = serialize('geojson', restaurants, geometry_field='location', fields=('name', 'address'))
    return JsonResponse(json.loads(data), safe=False)


# --- 4. API Đặt bàn (Booking) ---
@csrf_exempt
def api_book_table(request):
    """API xử lý việc đặt bàn từ bản đồ"""
    if request.method == 'POST':
        try:
            # Lấy dữ liệu
            restaurant_id = request.POST.get('restaurant_id')
            customer_name = request.POST.get('name')
            booking_time_str = request.POST.get('time')
            
            # Tìm quán
            restaurant = Restaurant.objects.get(id=restaurant_id)
            
            # Tìm bàn trống
            available_table = restaurant.tables.filter(is_available=True).first()
            
            if not available_table:
                return JsonResponse({'status': 'error', 'message': 'Rất tiếc, quán này đã hết bàn trống!'})
            
            # Tạo đơn đặt bàn
            Reservation.objects.create(
                table=available_table,
                customer_name=customer_name,
                booking_time=parse_datetime(booking_time_str), # Hàm này giờ đã chạy đúng
                number_of_people=4
            )
            
            # Cập nhật trạng thái bàn
            available_table.is_available = False
            available_table.save()
            
            return JsonResponse({
                'status': 'success', 
                'message': f'Thành công! Bạn đã đặt {available_table.table_number}.'
            })
            
        except Exception as e:
            print("Lỗi đặt bàn:", e)
            return JsonResponse({'status': 'error', 'message': 'Lỗi server: ' + str(e)})
            
    return JsonResponse({'status': 'error', 'message': 'Yêu cầu không hợp lệ'})