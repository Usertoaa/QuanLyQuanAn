import json
from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse
from django.core.serializers import serialize
from django.contrib.gis.geos import Point
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime 
from django.db.models import Q 
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib import messages as flash_msg
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import Restaurant, Table, Reservation, Dish, Feedback

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
            Q(address__icontains=search_query)
        )

    # Lọc theo Quận
    district_filter = request.GET.get('district')
    if district_filter:
        restaurants = restaurants.filter(district=district_filter)

    context = {
        'restaurants': restaurants,
        'districts': districts,
        'current_district': district_filter
    }
    return render(request, 'restaurants/index.html', context)


def restaurant_detail(request, pk):
    """Trang chi tiết quán ăn"""
    restaurant = get_object_or_404(Restaurant, pk=pk)
    
    # Lấy các đánh giá của quán
    feedbacks = restaurant.feedbacks.all()
    total_feedbacks = feedbacks.count()
    
    # Tính trung bình đánh giá
    if total_feedbacks > 0:
        average_rating = sum(f.rating for f in feedbacks) / total_feedbacks
    else:
        average_rating = 0
    
    # Đếm từng rating
    rating_counts = {
        1: feedbacks.filter(rating=1).count(),
        2: feedbacks.filter(rating=2).count(),
        3: feedbacks.filter(rating=3).count(),
        4: feedbacks.filter(rating=4).count(),
        5: feedbacks.filter(rating=5).count(),
    }
    
    context = {
        'restaurant': restaurant,
        'feedbacks': feedbacks[:5],  # Hiển thị 5 feedback gần nhất
        'total_feedbacks': total_feedbacks,
        'average_rating': round(average_rating, 1),
        'rating_counts': rating_counts
    }
    return render(request, 'restaurants/detail.html', context)


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
    """API tìm quán gần vị trí User"""
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
        radius = float(request.GET.get('radius', 5))

        user_location = Point(lng, lat, srid=4326)

        restaurants = Restaurant.objects.filter(
            location__distance_lte=(user_location, D(km=radius))
        ).annotate(
            distance=Distance('location', user_location)
        ).order_by('distance')

        data = []
        for r in restaurants:
            img_url = r.image.url if r.image else "https://placehold.co/600x400?text=No+Image"
            data.append({
                'id': r.id,
                'name': r.name,
                'address': r.address,
                'district': r.get_district_display(),
                'distance': round(r.distance.km, 1),
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
        image = request.FILES.get('image')
        lat = float(request.POST.get('lat'))
        lng = float(request.POST.get('lng'))
        pnt = Point(lng, lat, srid=4326)

        if restaurant:
            restaurant.name = name
            restaurant.address = address
            restaurant.district = district
            restaurant.location = pnt
            if image: restaurant.image = image
            restaurant.save()
            flash_msg.success(request, f"Đã cập nhật '{name}' thành công!")
        else: 
            Restaurant.objects.create(
                name=name, address=address, district=district,
                location=pnt, image=image
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
        flash_msg.success(request, "Đã thêm món mới!") 
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
        
        flash_msg.success(request, "Cập nhật món thành công!") 
        return redirect('admin_menu_list', pk=restaurant.pk)

    return render(request, 'restaurants/admin_dish_form.html', {'restaurant': restaurant, 'dish': dish, 'action': 'Sửa'})


@user_passes_test(lambda u: u.is_superuser)
def admin_dish_delete(request, dish_id):
    dish = get_object_or_404(Dish, pk=dish_id)
    restaurant_id = dish.restaurant.pk
    dish.delete()
    flash_msg.warning(request, "Đã xóa món ăn!") 
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
    
    # Lọc theo quán nếu có tham số
    selected_restaurant_id = request.GET.get('restaurant_id')
    selected_restaurant_name = None
    
    if selected_restaurant_id:
        bookings = bookings.filter(table__restaurant_id=selected_restaurant_id)
        selected_restaurant = Restaurant.objects.get(id=selected_restaurant_id)
        selected_restaurant_name = selected_restaurant.name
    
    all_restaurants = Restaurant.objects.all().order_by('name')
    
    return render(request, 'restaurants/admin_booking_list.html', {
        'bookings': bookings, 
        'is_global': True,
        'all_restaurants': all_restaurants,
        'selected_restaurant_id': selected_restaurant_id,
        'selected_restaurant_name': selected_restaurant_name
    })


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


# --- QUẢN LÝ PHẢN HỒI ---
def feedback_form(request, pk):
    """Trang form gửi phản hồi về quán ăn"""
    restaurant = get_object_or_404(Restaurant, pk=pk)
    
    if request.method == 'POST':
        customer_name = request.POST.get('customer_name')
        customer_email = request.POST.get('customer_email')
        rating = request.POST.get('rating')
        message = request.POST.get('message')
        
        # Tạo Feedback record
        feedback = Feedback.objects.create(
            restaurant=restaurant,
            customer_name=customer_name,
            customer_email=customer_email,
            rating=rating,
            message=message
        )
        
        # Gửi email thông báo cho Admin
        try:
            send_feedback_email_to_admin(feedback)
        except Exception as e:
            print(f"Lỗi gửi email admin: {e}")
        
        # Gửi email xác nhận cho khách hàng
        try:
            send_feedback_confirmation_email(feedback)
        except Exception as e:
            print(f"Lỗi gửi email xác nhận: {e}")
        
        flash_msg.success(request, "Cảm ơn bạn! Phản hồi của bạn đã được gửi thành công.")
        return redirect('restaurant_detail', pk=pk)
    
    context = {
        'restaurant': restaurant,
        'rating_choices': Feedback.RATING_CHOICES
    }
    return render(request, 'restaurants/feedback_form.html', context)


@user_passes_test(lambda u: u.is_superuser)
def admin_feedback_list(request, pk):
    """Xem phản hồi của 1 quán cụ thể"""
    restaurant = get_object_or_404(Restaurant, pk=pk)
    feedbacks = restaurant.feedbacks.all()
    
    context = {
        'restaurant': restaurant,
        'feedbacks': feedbacks,
        'total_feedbacks': feedbacks.count(),
        'active_page': 'feedbacks'
    }
    return render(request, 'restaurants/admin_feedback_list.html', context)


@user_passes_test(lambda u: u.is_superuser)
def admin_all_feedbacks(request):
    """Xem tất cả phản hồi trong hệ thống"""
    feedbacks = Feedback.objects.all().select_related('restaurant').order_by('-created_at')
    
    # Lọc theo quán nếu có
    restaurant_id = request.GET.get('restaurant_id')
    restaurant_name = None
    if restaurant_id:
        feedbacks = feedbacks.filter(restaurant_id=restaurant_id)
        restaurant_name = Restaurant.objects.get(id=restaurant_id).name
    
    # Lọc theo rating nếu có
    rating = request.GET.get('rating')
    if rating:
        feedbacks = feedbacks.filter(rating=rating)
    
    all_restaurants = Restaurant.objects.all().order_by('name')
    
    context = {
        'feedbacks': feedbacks,
        'all_restaurants': all_restaurants,
        'restaurant_id': restaurant_id,
        'restaurant_name': restaurant_name,
        'rating': rating,
        'active_page': 'feedbacks'
    }
    return render(request, 'restaurants/admin_all_feedbacks.html', context)


@user_passes_test(lambda u: u.is_superuser)
def admin_mark_feedback_as_read(request, feedback_id):
    """Đánh dấu phản hồi đã xem"""
    feedback = get_object_or_404(Feedback, pk=feedback_id)
    feedback.is_read = True
    feedback.save()
    flash_msg.success(request, "Đã đánh dấu phản hồi này là đã xem.")
    return redirect('admin_feedback_list', pk=feedback.restaurant.pk)


# ===== EMAIL FUNCTIONS =====

def send_feedback_email_to_admin(feedback):
    """Gửi email thông báo phản hồi mới đến Admin"""
    subject = f"🔔 Phản hồi mới từ {feedback.customer_name} - {feedback.restaurant.name}"
    
    html_message = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                <!-- Header -->
                <div style="background-color: #dc3545; color: white; padding: 20px; text-align: center;">
                    <h2 style="margin: 0;">📝 Phản hồi từ khách hàng</h2>
                </div>
                
                <!-- Content -->
                <div style="padding: 20px;">
                    <p><strong>Quán ăn:</strong> {feedback.restaurant.name}</p>
                    <p><strong>Tên khách hàng:</strong> {feedback.customer_name}</p>
                    <p><strong>Email:</strong> {feedback.customer_email}</p>
                    <p><strong>Đánh giá:</strong> {feedback.get_rating_display()}</p>
                    <p><strong>Thời gian:</strong> {feedback.created_at.strftime('%d/%m/%Y %H:%M')}</p>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                    
                    <h4>Nội dung phản hồi:</h4>
                    <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #dc3545; border-radius: 4px;">
                        <p>{feedback.message}</p>
                    </div>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                    
                    <!-- CTA Button -->
                    <div style="text-align: center; margin: 20px 0;">
                        <a href="http://localhost:8000/my-admin/restaurant/{feedback.restaurant.id}/feedbacks/" 
                           style="background-color: #dc3545; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                            👁️ Xem chi tiết
                        </a>
                    </div>
                </div>
                
                <!-- Footer -->
                <div style="background-color: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; color: #666;">
                    <p>GIS Eatery © 2026 | Hệ thống quản lý quán ăn</p>
                </div>
            </div>
        </body>
    </html>
    """
    
    plain_message = strip_tags(html_message)
    
    send_mail(
        subject=subject,
        message=plain_message,
        from_email='noreply@giseatery.com',
        recipient_list=['admin@giseatery.com'],
        html_message=html_message,
        fail_silently=False,
    )


def send_feedback_confirmation_email(feedback):
    """Gửi email xác nhận cho khách hàng sau khi gửi phản hồi"""
    subject = "✅ Phản hồi của bạn đã được nhận"
    
    html_message = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                <!-- Header -->
                <div style="background-color: #28a745; color: white; padding: 20px; text-align: center;">
                    <h2 style="margin: 0;">✅ Cảm ơn bạn!</h2>
                </div>
                
                <!-- Content -->
                <div style="padding: 20px;">
                    <p>Xin chào <strong>{feedback.customer_name}</strong>,</p>
                    
                    <p>Cảm ơn bạn đã gửi phản hồi cho quán ăn <strong>{feedback.restaurant.name}</strong>.</p>
                    
                    <p>Chúng tôi sẽ xem xét phản hồi của bạn trong vòng 24 giờ và sẽ liên hệ với bạn nếu cần thêm thông tin.</p>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                    
                    <h4>Thông tin phản hồi của bạn:</h4>
                    <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #28a745; border-radius: 4px;">
                        <p><strong>Quán ăn:</strong> {feedback.restaurant.name}</p>
                        <p><strong>Đánh giá:</strong> {feedback.get_rating_display()}</p>
                        <p><strong>Ngày gửi:</strong> {feedback.created_at.strftime('%d/%m/%Y %H:%M')}</p>
                    </div>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                    
                    <p style="color: #666; font-size: 14px;">
                        Nếu bạn có thắc mắc, vui lòng liên hệ với chúng tôi qua email này.
                    </p>
                </div>
                
                <!-- Footer -->
                <div style="background-color: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; color: #666;">
                    <p>GIS Eatery © 2026 | Hệ thống quản lý quán ăn</p>
                    <p>Email này được gửi tự động, vui lòng không trả lời email này.</p>
                </div>
            </div>
        </body>
    </html>
    """
    
    plain_message = strip_tags(html_message)
    
    send_mail(
        subject=subject,
        message=plain_message,
        from_email='noreply@giseatery.com',
        recipient_list=[feedback.customer_email],
        html_message=html_message,
        fail_silently=False,
    )