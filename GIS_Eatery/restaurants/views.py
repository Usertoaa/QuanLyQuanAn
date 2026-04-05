import json
from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse
from django.core.serializers import serialize
from django.contrib.gis.geos import Point
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime 
from django.db.models import Q, Min
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib import messages as flash_msg 
from .models import Restaurant, Table, Reservation, Dish, RestaurantImage

# PHẦN 1: PUBLIC USER VIEWS (Giao diện cho người dùng)

def index(request):
    """Trang chủ: Tìm kiếm, Lọc và Hiển thị danh sách"""
    districts = Restaurant.DISTRICT_CHOICES
    restaurants = Restaurant.objects.all().order_by('-created_at')

    # Tìm kiếm
    search_query = request.GET.get('q')
    if search_query:
        restaurants = restaurants.filter(
            Q(name__icontains=search_query) |
            Q(address__icontains=search_query) |
            Q(dishes__name__icontains=search_query)
        ).distinct()

    # Lọc theo Quận
    district_filter = request.GET.get('district')
    if district_filter:
        restaurants = restaurants.filter(district=district_filter)

    # Sắp xếp rẻ nhất
    sort = request.GET.get('sort')
    if sort == 'cheap':
        restaurants = restaurants.annotate(
            min_price=Min('dishes__price')
        ).order_by('min_price', '-created_at')

    context = {
        'restaurants': restaurants,
        'districts': districts,
        'current_district': district_filter,
        'current_sort': sort,
    }
    return render(request, 'restaurants/index.html', context)


def restaurant_detail(request, pk):
    """Trang chi tiết quán ăn"""
    restaurant = get_object_or_404(Restaurant, pk=pk)
    return render(request, 'restaurants/detail.html', {'restaurant': restaurant})


def user_map(request):
    """Giao diện bản đồ"""
    return render(request, 'restaurants/user_map.html')


def map_detail(request, pk):
    """Bản đồ chi tiết cho một quán ăn cụ thể"""
    restaurant = get_object_or_404(Restaurant, pk=pk)
    return render(request, 'restaurants/map.html', {'restaurant': restaurant})


def map_view(request):
    """Alias cho user_map (để tương thích ngược)"""
    return render(request, 'restaurants/user_map.html')


# PHẦN 2: AUTHENTICATION & USER PROFILE 

def register_view(request):
    """Đăng ký thành viên"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            flash_msg.success(request, f"Chào mừng {user.username}!") 
            return redirect('index')
        else:
            flash_msg.error(request, "Lỗi đăng ký. Vui lòng kiểm tra lại thông tin.")
    else:
        form = UserCreationForm()
    
    return render(request, 'restaurants/register.html', {'form': form})


@login_required(login_url='login')
def user_booking_history(request):
    """Lịch sử đặt bàn của người dùng đang đăng nhập"""
    my_bookings = Reservation.objects.filter(user=request.user).select_related('table__restaurant').order_by('-booking_time')
    return render(request, 'restaurants/user_history.html', {'bookings': my_bookings})


# PHẦN 3: API ENDPOINTS (AJAX/JSON cho Bản đồ và Đặt bàn)

def api_get_restaurants(request):
    """API trả về dữ liệu GeoJSON của toàn bộ quán"""
    restaurants = Restaurant.objects.all()
    data = serialize('geojson', restaurants, geometry_field='location', fields=('name', 'address'))
    return JsonResponse(json.loads(data), safe=False)


def api_nearby_restaurants(request):
    """API tìm quán gần vị trí User, có thể lọc theo tên quán / địa chỉ / món ăn"""
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
        radius = float(request.GET.get('radius', 10))
        sort = request.GET.get('sort', 'near')
        keyword = request.GET.get('q', '').strip()

        user_location = Point(lng, lat, srid=4326)

        restaurants = Restaurant.objects.filter(
            location__distance_lte=(user_location, D(km=radius))
        )

        # Lọc theo từ khóa nếu có
        if keyword:
            restaurants = restaurants.filter(
                Q(name__icontains=keyword) |
                Q(address__icontains=keyword) |
                Q(dishes__name__icontains=keyword)
            ).distinct()

        restaurants = restaurants.annotate(
            distance=Distance('location', user_location),
            min_price=Min('dishes__price')
        )

        if sort == 'cheap':
            restaurants = restaurants.order_by('min_price', 'distance')
        else:
            restaurants = restaurants.order_by('distance')

        data = []
        for r in restaurants:
            img_url = r.image.url if r.image else "https://placehold.co/600x400?text=No+Image"
            data.append({
                'id': r.id,
                'name': r.name,
                'address': r.address,
                'district': r.get_district_display(),
                'distance': round(r.distance.km, 1) if r.distance else None,
                'min_price': int(r.min_price) if r.min_price else None,
                'image': img_url,
                'lat': r.location.y,
                'lng': r.location.x
            })

        return JsonResponse(data, safe=False)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
def api_book_table(request):
    """API Xử lý đặt bàn (Đã sửa lỗi logic Form)"""
    if request.method == 'POST':
        try:
            # 1. Lấy dữ liệu
            restaurant_id = request.POST.get('restaurant_id')
            customer_name = request.POST.get('name')
            booking_time_str = request.POST.get('time')
            people = request.POST.get('people', 4) # Mặc định 4 nếu thiếu
            
            # 2. Tìm quán & Bàn trống
            restaurant = Restaurant.objects.get(id=restaurant_id)
            available_table = restaurant.tables.filter(is_available=True).first()
            
            if not available_table:
                available_table = restaurant.tables.first() 
            
            if not available_table:
                return JsonResponse({'status': 'error', 'message': 'Quán này chưa set-up bàn ghế!'})
            # 3. Tạo đơn đặt bàn
            reservation = Reservation(
                table=available_table,
                customer_name=customer_name,
                booking_time=parse_datetime(booking_time_str),
                number_of_people=int(people),
                status='pending'
            )

            # 4. Gắn user nếu đã đăng nhập
            if request.user.is_authenticated:
                reservation.user = request.user
            
            reservation.save()
            
            return JsonResponse({
                'status': 'success', 
                'message': f'Thành công! Đơn đặt tại {restaurant.name} đang chờ duyệt.'
            })
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': 'Lỗi server: ' + str(e)})
            
    return JsonResponse({'status': 'error', 'message': 'Yêu cầu không hợp lệ'})

# PHẦN 4: ADMIN DASHBOARD & MANAGEMENT (Quản trị viên)

@user_passes_test(lambda u: u.is_superuser) 
def admin_dashboard(request):
    context = {
        'total_restaurants': Restaurant.objects.count(),
        'total_reservations': Reservation.objects.count(),
        'total_tables': Table.objects.count(),
        'active_page': 'dashboard'
    }
    return render(request, 'restaurants/admin_dashboard.html', context)


# --- QUẢN LÝ QUÁN ĂN ---
@user_passes_test(lambda u: u.is_superuser)
def admin_restaurant_list(request):
    restaurants = Restaurant.objects.all().order_by('-created_at')
    context = {
        'restaurants': restaurants,
        'active_page': 'restaurants'
    }
    return render(request, 'restaurants/admin_manage.html', context)


@user_passes_test(lambda u: u.is_superuser)
def admin_restaurant_form(request, pk=None):
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
        image = request.FILES.get('image')  # ảnh đại diện
        gallery_images = request.FILES.getlist('gallery_images')  # nhiều ảnh
        lat = float(request.POST.get('lat'))
        lng = float(request.POST.get('lng'))
        pnt = Point(lng, lat, srid=4326)

        if restaurant:
            restaurant.name = name
            restaurant.address = address
            restaurant.district = district
            restaurant.location = pnt
            if image:
                restaurant.image = image
            restaurant.save()

            # thêm ảnh mới vào album
            for img in gallery_images:
                RestaurantImage.objects.create(
                    restaurant=restaurant,
                    image=img
                )

            flash_msg.success(request, f"Đã cập nhật '{name}' thành công!")
        else:
            restaurant = Restaurant.objects.create(
                name=name,
                address=address,
                district=district,
                location=pnt,
                image=image
            )

            for img in gallery_images:
                RestaurantImage.objects.create(
                    restaurant=restaurant,
                    image=img
                )

            flash_msg.success(request, f"Đã thêm '{name}' thành công!")

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
    flash_msg.warning(request, "Đã xóa quán ăn!") 
    return redirect('admin_restaurant_list')


# --- QUẢN LÝ THỰC ĐƠN (MENU) ---
@user_passes_test(lambda u: u.is_superuser)
def admin_menu_list(request, pk):
    restaurant = get_object_or_404(Restaurant, pk=pk)
    dishes = restaurant.dishes.all() 
    return render(request, 'restaurants/admin_menu_list.html', {'restaurant': restaurant, 'dishes': dishes})


@user_passes_test(lambda u: u.is_superuser)
def admin_dish_form(request, pk):
    restaurant = get_object_or_404(Restaurant, pk=pk)
    
    if request.method == "POST":
        Dish.objects.create(
            restaurant=restaurant,
            name=request.POST.get('name'),
            price=request.POST.get('price'),
            description=request.POST.get('description'),
            image=request.FILES.get('image'),
            is_available=request.POST.get('is_available') == 'on'
        )
        flash_msg.success(request, "Đã thêm món mới!") # Đã sửa messages -> flash_msg
        return redirect('admin_menu_list', pk=pk)

    return render(request, 'restaurants/admin_dish_form.html', {'restaurant': restaurant, 'action': 'Thêm'})


@user_passes_test(lambda u: u.is_superuser)
def admin_dish_edit(request, dish_id):
    dish = get_object_or_404(Dish, pk=dish_id)
    restaurant = dish.restaurant

    if request.method == "POST":
        dish.name = request.POST.get('name')
        dish.price = request.POST.get('price')
        dish.description = request.POST.get('description')
        if request.FILES.get('image'):
            dish.image = request.FILES.get('image')
        dish.is_available = request.POST.get('is_available') == 'on'
        dish.save()
        
        flash_msg.success(request, "Cập nhật món thành công!") # Đã sửa messages -> flash_msg
        return redirect('admin_menu_list', pk=restaurant.pk)

    return render(request, 'restaurants/admin_dish_form.html', {'restaurant': restaurant, 'dish': dish, 'action': 'Sửa'})


@user_passes_test(lambda u: u.is_superuser)
def admin_dish_delete(request, dish_id):
    dish = get_object_or_404(Dish, pk=dish_id)
    restaurant_id = dish.restaurant.pk
    dish.delete()
    flash_msg.warning(request, "Đã xóa món ăn!") # Đã sửa messages -> flash_msg
    return redirect('admin_menu_list', pk=restaurant_id)


# --- QUẢN LÝ ĐẶT BÀN ---
@user_passes_test(lambda u: u.is_superuser)
def admin_booking_list(request, pk):
    """Xem đơn đặt bàn của 1 quán cụ thể"""
    restaurant = get_object_or_404(Restaurant, pk=pk)
    bookings = Reservation.objects.filter(table__restaurant=restaurant).order_by('-booking_time')
    return render(request, 'restaurants/admin_booking_list.html', {'restaurant': restaurant, 'bookings': bookings})


@user_passes_test(lambda u: u.is_superuser)
def admin_all_bookings(request):
    """Xem đơn đặt bàn toàn hệ thống (Optional)"""
    bookings = Reservation.objects.all().select_related('table__restaurant').order_by('-booking_time')
    return render(request, 'restaurants/admin_booking_list.html', {'bookings': bookings, 'is_global': True})


@user_passes_test(lambda u: u.is_superuser)
def admin_update_booking_status(request, booking_id, status):
    """Duyệt hoặc Hủy đơn"""
    booking = get_object_or_404(Reservation, pk=booking_id)
    
    if status in ['confirmed', 'cancelled', 'pending']:
        booking.status = status
        booking.save()
        flash_msg.success(request, f"Đã cập nhật trạng thái đơn của {booking.customer_name} thành công!")
    else:
        flash_msg.error(request, "Trạng thái không hợp lệ!")
        
    return redirect('admin_booking_list', pk=booking.table.restaurant.pk)