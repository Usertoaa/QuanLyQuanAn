from pyexpat.errors import messages
from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse
from django.core.serializers import serialize
from django.contrib.gis.geos import Point
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime 
from .models import Restaurant, Table, Reservation
from django.db.models import Q 
from django.contrib.auth.decorators import login_required, user_passes_test
import json

def is_admin(user):
    return user.is_superuser

@user_passes_test(is_admin) 
def admin_dashboard(request):
    context = {
        'total_restaurants': Restaurant.objects.count(),
        'total_reservations': Reservation.objects.count(),
        'total_tables': Table.objects.count(),
        'active_page': 'dashboard' # Để tô màu menu
    }
    return render(request, 'restaurants/admin_dashboard.html', context)

@user_passes_test(lambda u: u.is_superuser)
def admin_restaurant_list(request):
    restaurants = Restaurant.objects.all().order_by('-created_at')
    context = {
        'restaurants': restaurants,
        'active_page': 'restaurants' # Để tô màu menu
    }
    return render(request, 'restaurants/admin_manage.html', context)

@user_passes_test(lambda u: u.is_superuser)
def admin_reservations(request):
    # Lấy danh sách mới nhất lên đầu
    reservations = Reservation.objects.select_related('table', 'table__restaurant').order_by('-booking_time')
    
    context = {
        'reservations': reservations,
        'active_page': 'reservations'
    }
    return render(request, 'restaurants/admin_reservations.html', context)

@user_passes_test(lambda u: u.is_superuser)
def admin_restaurant_form(request, pk=None):
    # Nếu có pk -> Là Sửa (Lấy dữ liệu cũ) | Nếu không -> Là Thêm mới
    if pk:
        restaurant = get_object_or_404(Restaurant, pk=pk)
        action_title = "CẬP NHẬT QUÁN ĂN"
    else:
        restaurant = None
        action_title = "THÊM QUÁN MỚI"

    if request.method == "POST":
        name = request.POST.get('name')
        address = request.POST.get('address')
        district = request.POST.get('district')
        image = request.FILES.get('image')
        lat = float(request.POST.get('lat'))
        lng = float(request.POST.get('lng'))
        pnt = Point(lng, lat, srid=4326)

        if restaurant: # Đang sửa
            restaurant.name = name
            restaurant.address = address
            restaurant.district = district
            restaurant.location = pnt
            if image: restaurant.image = image # Chỉ đổi ảnh nếu user upload ảnh mới
            restaurant.save()
            messages.success(request, f"Đã cập nhật '{name}' thành công!")
        else: # Đang thêm
            Restaurant.objects.create(
                name=name, address=address, district=district,
                location=pnt, image=image
            )
            messages.success(request, f"Đã thêm '{name}' thành công!")

        return redirect('admin_restaurant_list')

    context = {
        'restaurant': restaurant, 
        'districts': Restaurant.DISTRICT_CHOICES,
        'action_title': action_title,
        'active_page': 'restaurants'
    }
    return render(request, 'restaurants/admin_form.html', context)

@user_passes_test(lambda u: u.is_superuser)
def admin_restaurant_delete(request, pk):
    restaurant = get_object_or_404(Restaurant, pk=pk)
    restaurant.delete()
    messages.warning(request, "Đã xóa quán ăn!")
    return redirect('admin_restaurant_list')

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

def index(request):
    # 1. Lấy danh sách quận để hiển thị trong menu lọc
    districts = Restaurant.DISTRICT_CHOICES
    
    # 2. Lấy tất cả quán ăn
    restaurants = Restaurant.objects.all().order_by('-created_at')

    # 3. Xử lý Tìm kiếm (theo tên hoặc địa chỉ)
    search_query = request.GET.get('q')
    if search_query:
        restaurants = restaurants.filter(
            Q(name__icontains=search_query) | 
            Q(address__icontains=search_query)
        )

    # 4. Xử lý Lọc theo Quận
    district_filter = request.GET.get('district')
    if district_filter:
        restaurants = restaurants.filter(district=district_filter)

    context = {
        'restaurants': restaurants,
        'districts': districts,
        'current_district': district_filter
    }
    return render(request, 'restaurants/index.html', context)