import requests
from datetime import datetime, timedelta
import uuid
import hashlib
import os
from django.http import FileResponse
from io import BytesIO

from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse
from django.contrib.gis.geos import Point
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.db.models import Q, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
from django.contrib.auth.models import User
from django.contrib import messages as flash_msg
from django.core.mail import send_mail
from django.utils.html import strip_tags
from django.urls import reverse

from .models import (
    Restaurant,
    Table,
    Reservation,
    ReservationItem,
    Dish,
    Feedback,
    RestaurantImage,
    PickupOrder,
    PickupOrderItem,
    UserProfile,
    PasswordResetToken,
)
from .forms import CustomUserCreationForm, CustomSetPasswordForm, DishImportForm
from .import_dishes_from_excel import DishImportHandler

# ============================================
# CONSTANTS
# ============================================
BOOKING_SLOT_MINUTES = 30
ADVANCE_BOOKING_MINUTES = 90  # Không được đặt sớm quá 90 phút
ACTIVE_RESERVATION_STATUSES = ['pending', 'confirmed', 'waiting']


# ============================================
# UTILITY FUNCTIONS - BOOKING & TIME
# ============================================

def validate_booking_time(requested_time):
    """
    Kiểm tra thời gian đặt bàn có hợp lệ không
    - Không được đặt sớm quá 90 phút
    - Không được đặt ở quá khứ
    
    Returns: (is_valid, error_message)
    """
    now = timezone.now()
    min_booking_time = now + timedelta(minutes=ADVANCE_BOOKING_MINUTES)
    
    # Kiểm tra thời gian đặt ở quá khứ
    if requested_time < now:
        return False, "⚠️ Thời gian đặt không thể ở quá khứ!"
    
    # Kiểm tra đặt sớm quá 90 phút
    if requested_time < min_booking_time:
        remaining_minutes = int((min_booking_time - now).total_seconds() / 60)
        return False, f"⚠️ Vui lòng đặt bàn trễ hơn {ADVANCE_BOOKING_MINUTES} phút. Thời gian sớm nhất có thể: {min_booking_time.strftime('%d/%m/%Y %H:%M')}"
    
    return True, ""


def get_restaurant_display_image(restaurant):
    if getattr(restaurant, 'image', None):
        try:
            return restaurant.image.url
        except Exception:
            pass

    first_gallery = restaurant.gallery_images.first()
    if first_gallery and first_gallery.image:
        try:
            return first_gallery.image.url
        except Exception:
            pass

    return '/static/default-restaurant.jpg'


def parse_user_datetime(raw_value):
    if not raw_value:
        return None

    dt = parse_datetime(raw_value)
    if dt is None:
        formats = [
            '%m/%d/%Y %I:%M %p',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%dT%H:%M',
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(raw_value, fmt)
                break
            except ValueError:
                continue

    if dt is None:
        return None

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())

    return dt


def create_default_tables_for_restaurant(restaurant):
    if restaurant.tables.exists():
        return

    Table.objects.bulk_create([
        Table(restaurant=restaurant, table_number='Bàn 1', capacity=4, is_available=True),
        Table(restaurant=restaurant, table_number='Bàn 2', capacity=4, is_available=True),
        Table(restaurant=restaurant, table_number='Bàn 3', capacity=4, is_available=True),
        Table(restaurant=restaurant, table_number='Bàn 4', capacity=8, is_available=True),
    ])


def compute_table_available_from(table, requested_time):
    slot_delta = timedelta(minutes=BOOKING_SLOT_MINUTES)

    reservations = Reservation.objects.filter(
        table=table,
        status__in=ACTIVE_RESERVATION_STATUSES
    ).order_by('booking_time')

    available_from = requested_time

    for reservation in reservations:
        reservation_start = reservation.booking_time
        reservation_end = reservation.booking_time + slot_delta

        if reservation_end <= available_from:
            continue

        if reservation_start <= available_from < reservation_end:
            available_from = reservation_end

    return available_from


def find_best_table_for_booking(restaurant, people, requested_time):
    candidate_tables = restaurant.tables.filter(
        is_available=True,
        capacity__gte=people
    ).order_by('capacity', 'id')

    best_table = None
    best_time = None

    for table in candidate_tables:
        available_from = compute_table_available_from(table, requested_time)

        if best_time is None or available_from < best_time:
            best_table = table
            best_time = available_from

    return best_table, best_time


# ============================================
# PUBLIC VIEWS - USER INTERFACE
# ============================================

def index(request):
    districts = Restaurant.DISTRICT_CHOICES

    representative_qs = Dish.objects.filter(
        restaurant=OuterRef('pk'),
        is_available=True,
        is_price_representative=True
    ).order_by('price')

    fallback_qs = Dish.objects.filter(
        restaurant=OuterRef('pk'),
        is_available=True
    ).order_by('price')

    restaurants = Restaurant.objects.prefetch_related('gallery_images').annotate(
        min_price=Coalesce(
            Subquery(representative_qs.values('price')[:1]),
            Subquery(fallback_qs.values('price')[:1])
        ),
        cheapest_dish_name=Coalesce(
            Subquery(representative_qs.values('name')[:1]),
            Subquery(fallback_qs.values('name')[:1])
        )
    ).order_by('-created_at')

    search_query = request.GET.get('q')
    if search_query:
        restaurants = restaurants.filter(
            Q(name__icontains=search_query) |
            Q(address__icontains=search_query) |
            Q(dishes__name__icontains=search_query)
        ).distinct()

    district_filter = request.GET.get('district')
    if district_filter:
        restaurants = restaurants.filter(district=district_filter)

    sort = request.GET.get('sort')
    if sort == 'cheap':
        restaurants = restaurants.order_by('min_price', '-created_at')

    for restaurant in restaurants:
        restaurant.display_image_url = get_restaurant_display_image(restaurant)

    context = {
        'restaurants': restaurants,
        'districts': districts,
        'current_district': district_filter,
        'current_sort': sort,
    }
    return render(request, 'restaurants/index.html', context)


def restaurant_detail(request, pk):
    restaurant = get_object_or_404(
        Restaurant.objects.prefetch_related('gallery_images', 'feedbacks'),
        pk=pk
    )

    feedbacks = restaurant.feedbacks.all().order_by('-created_at')
    gallery_images = restaurant.gallery_images.all()
    total_feedbacks = feedbacks.count()

    if total_feedbacks > 0:
        average_rating = sum(f.rating for f in feedbacks) / total_feedbacks
    else:
        average_rating = 0

    rating_counts = {
        1: feedbacks.filter(rating=1).count(),
        2: feedbacks.filter(rating=2).count(),
        3: feedbacks.filter(rating=3).count(),
        4: feedbacks.filter(rating=4).count(),
        5: feedbacks.filter(rating=5).count(),
    }

    context = {
        'restaurant': restaurant,
        'feedbacks': feedbacks[:5],
        'total_feedbacks': total_feedbacks,
        'average_rating': round(average_rating, 1),
        'rating_counts': rating_counts,
        'gallery_images': gallery_images,
        'main_image_url': get_restaurant_display_image(restaurant),
    }
    return render(request, 'restaurants/detail.html', context)


def user_map(request):
    return render(request, 'restaurants/user_map.html')


def map_detail(request, pk):
    restaurant = get_object_or_404(Restaurant, pk=pk)
    return render(request, 'restaurants/user_map.html', {'restaurant': restaurant})


def map_view(request):
    return render(request, 'restaurants/user_map.html')


# PHẦN 2: AUTHENTICATION & USER PROFILE

def register_view(request):
    """
    Đăng ký tài khoản mới với xác thực email
    """
    if request.user.is_authenticated:
        return redirect('index')
    
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # Chưa kích hoạt cho đến khi xác thực email
            user.save()
            
            # Tạo UserProfile và gửi email xác thực
            send_verification_email(request, user)
            
            flash_msg.success(
                request,
                'Đăng ký thành công! Vui lòng kiểm tra email để xác thực tài khoản.'
            )
            return redirect('verification_pending')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash_msg.error(request, f'{field}: {error}')
    else:
        form = CustomUserCreationForm()

    return render(request, 'restaurants/register.html', {'form': form})


def send_verification_email(request, user):
    """
    Gửi email xác thực cho người dùng
    """
    # Tạo hoặc lấy UserProfile
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    # Tạo token xác thực
    verification_token = hashlib.sha256(f'{user.id}{uuid.uuid4()}'.encode()).hexdigest()
    profile.email_verification_token = verification_token
    profile.email_verification_expires = timezone.now() + timedelta(hours=24)
    profile.save()
    
    # Tạo link xác thực
    verification_link = request.build_absolute_uri(
        reverse('verify_email', kwargs={'token': verification_token})
    )
    
    # Nội dung email
    subject = '🔐 Xác thực email - GIS Eatery'
    html_message = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 10px;">
                <h2 style="color: #cf2127; text-align: center;">🍽️ Chào mừng đến GIS Eatery!</h2>
                <p>Xin chào <strong>{user.username}</strong>,</p>
                <p>Cảm ơn bạn đã đăng ký tài khoản. Vui lòng nhấp vào link dưới đây để xác thực email:</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verification_link}" 
                       style="display: inline-block; padding: 12px 30px; background-color: #cf2127; 
                              color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
                        Xác thực email
                    </a>
                </div>
                
                <p>Hoặc sao chép link dưới đây vào trình duyệt:</p>
                <p style="background-color: #e9ecef; padding: 10px; border-radius: 5px; word-break: break-all;">
                    {verification_link}
                </p>
                
                <p style="color: #999; font-size: 12px;">
                    <strong>Lưu ý:</strong> Link xác thực sẽ hết hạn sau 24 giờ.
                </p>
                
                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">
                    Nếu bạn không đăng ký tài khoản này, vui lòng bỏ qua email này.
                </p>
            </div>
        </body>
    </html>
    """
    
    send_mail(
        subject,
        strip_tags(html_message),
        'noreply@giseatery.com',
        [user.email],
        html_message=html_message,
        fail_silently=False,
    )


def verify_email(request, token):
    """
    Xác thực email bằng token
    """
    try:
        profile = UserProfile.objects.get(email_verification_token=token)
        
        # Kiểm tra token còn hiệu lực không
        if profile.email_verification_expires < timezone.now():
            flash_msg.error(request, 'Token xác thực đã hết hạn. Vui lòng đăng ký lại.')
            return redirect('register')
        
        # Kích hoạt tài khoản
        user = profile.user
        user.is_active = True
        user.save()
        
        profile.email_verified = True
        profile.email_verification_token = ''
        profile.email_verification_expires = None
        profile.save()
        
        flash_msg.success(request, '✅ Email xác thực thành công! Bạn có thể đăng nhập ngay.')
        return redirect('verification_success')
    
    except UserProfile.DoesNotExist:
        flash_msg.error(request, 'Token xác thực không hợp lệ.')
        return redirect('register')


def verification_success(request):
    """
    Trang xác thực email thành công
    """
    return render(request, 'restaurants/verification_success.html')


def verification_pending(request):
    """
    Trang chờ xác thực email
    """
    return render(request, 'restaurants/verification_pending.html')


@csrf_exempt
def api_resend_verification_email(request):
    """
    API để gửi lại email xác thực (POST)
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Chỉ hỗ trợ POST'}, status=405)
    
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Bạn chưa đăng nhập'}, status=401)
    
    try:
        user = request.user
        
        # Kiểm tra nếu email đã xác thực
        profile = UserProfile.objects.get(user=user)
        if profile.email_verified:
            return JsonResponse({'success': False, 'error': 'Email của bạn đã được xác thực'})
        
        # Gửi lại email xác thực
        send_verification_email(request, user)
        
        return JsonResponse({'success': True, 'message': 'Email xác thực đã được gửi lại'})
    
    except UserProfile.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy profile người dùng'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Lỗi: {str(e)}'}, status=500)


def forgot_password(request):
    """
    Yêu cầu reset mật khẩu
    """
    if request.user.is_authenticated:
        return redirect('index')
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        
        try:
            user = User.objects.get(email=email, is_active=True)
            
            # Xóa các token cũ
            PasswordResetToken.objects.filter(user=user, is_used=False).delete()
            
            # Tạo token mới
            reset_token = hashlib.sha256(f'{user.id}{uuid.uuid4()}'.encode()).hexdigest()
            token_obj = PasswordResetToken.objects.create(
                user=user,
                token=reset_token,
                expires_at=timezone.now() + timedelta(hours=1)
            )
            
            # Gửi email reset
            reset_link = request.build_absolute_uri(
                reverse('reset_password', kwargs={'token': reset_token})
            )
            
            subject = '🔑 Reset mật khẩu - GIS Eatery'
            html_message = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 10px;">
                        <h2 style="color: #cf2127; text-align: center;">🔐 Reset mật khẩu</h2>
                        <p>Xin chào <strong>{user.username}</strong>,</p>
                        <p>Chúng tôi nhận được yêu cầu reset mật khẩu. Nhấp vào link dưới đây để tạo mật khẩu mới:</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{reset_link}" 
                               style="display: inline-block; padding: 12px 30px; background-color: #cf2127; 
                                      color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
                                Reset mật khẩu
                            </a>
                        </div>
                        
                        <p style="color: #999; font-size: 12px;">
                            <strong>Lưu ý:</strong> Link sẽ hết hạn sau 1 giờ.
                        </p>
                        
                        <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                        <p style="color: #999; font-size: 12px; text-align: center;">
                            Nếu bạn không yêu cầu reset mật khẩu, vui lòng bỏ qua email này.
                        </p>
                    </div>
                </body>
            </html>
            """
            
            send_mail(
                subject,
                strip_tags(html_message),
                'noreply@giseatery.com',
                [user.email],
                html_message=html_message,
                fail_silently=False,
            )
            
            flash_msg.success(request, 'Email reset mật khẩu đã được gửi. Vui lòng kiểm tra email.')
            return redirect('login')
        
        except User.DoesNotExist:
            # Không tiết lộ rằng email không tồn tại (bảo mật)
            flash_msg.success(request, 'Nếu email tồn tại, bạn sẽ nhận được hướng dẫn reset.')
            return redirect('login')
    
    return render(request, 'restaurants/forgot_password.html')


def reset_password(request, token):
    """
    Reset mật khẩu bằng token
    """
    try:
        token_obj = PasswordResetToken.objects.get(
            token=token,
            is_used=False,
            expires_at__gt=timezone.now()
        )
        user = token_obj.user
        
        if request.method == 'POST':
            form = CustomSetPasswordForm(user, request.POST)
            if form.is_valid():
                new_password = form.cleaned_data['new_password1']
                user.set_password(new_password)
                user.save()
                
                # Đánh dấu token đã sử dụng
                token_obj.is_used = True
                token_obj.save()
                
                flash_msg.success(request, '✅ Mật khẩu đã được reset thành công. Hãy đăng nhập!')
                return redirect('login')
        else:
            form = CustomSetPasswordForm(user)
        
        return render(request, 'restaurants/reset_password.html', {'form': form, 'token': token})
    
    except PasswordResetToken.DoesNotExist:
        flash_msg.error(request, 'Token reset mật khẩu không hợp lệ hoặc đã hết hạn.')
        return redirect('forgot_password')


@login_required(login_url='login')
def user_booking_history(request):
    my_bookings = Reservation.objects.filter(
        user=request.user
    ).select_related('table__restaurant').order_by('-booking_time')
    return render(request, 'restaurants/user_history.html', {'bookings': my_bookings})


# ============================================
# API ENDPOINTS - RESTAURANT & BOOKING DATA
# ============================================

def api_get_restaurants(request):
    # Hỗ trợ lọc theo ID nếu có tham số id
    restaurant_id = request.GET.get('id')
    
    if restaurant_id:
        restaurants = Restaurant.objects.prefetch_related('gallery_images').filter(id=restaurant_id)
    else:
        restaurants = Restaurant.objects.prefetch_related('gallery_images').all()
    
    data = []

    for r in restaurants:
        data.append({
            'id': r.id,
            'name': r.name,
            'address': r.address,
            'district': r.get_district_display(),
            'latitude': r.location.y,
            'longitude': r.location.x,
            'lat': r.location.y,
            'lng': r.location.x,
            'image': get_restaurant_display_image(r)
        })

    return JsonResponse(data, safe=False)


def api_nearby_restaurants(request):
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
        radius = float(request.GET.get('radius', 10))
        sort = request.GET.get('sort', 'near')
        keyword = request.GET.get('q', '').strip()

        user_location = Point(lng, lat, srid=4326)

        representative_qs = Dish.objects.filter(
            restaurant=OuterRef('pk'),
            is_available=True,
            is_price_representative=True
        ).order_by('price')

        fallback_qs = Dish.objects.filter(
            restaurant=OuterRef('pk'),
            is_available=True
        ).order_by('price')

        restaurants = Restaurant.objects.prefetch_related('gallery_images').filter(
            location__distance_lte=(user_location, D(km=radius))
        )

        if keyword:
            restaurants = restaurants.filter(
                Q(name__icontains=keyword) |
                Q(address__icontains=keyword) |
                Q(dishes__name__icontains=keyword)
            ).distinct()

        restaurants = restaurants.annotate(
            distance=Distance('location', user_location),
            min_price=Coalesce(
                Subquery(representative_qs.values('price')[:1]),
                Subquery(fallback_qs.values('price')[:1])
            ),
            cheapest_dish_name=Coalesce(
                Subquery(representative_qs.values('name')[:1]),
                Subquery(fallback_qs.values('name')[:1])
            )
        )

        if sort == 'cheap':
            restaurants = restaurants.order_by('min_price', 'distance')
        else:
            restaurants = restaurants.order_by('distance')

        data = []
        for r in restaurants:
            data.append({
                'id': r.id,
                'name': r.name,
                'address': r.address,
                'district': r.get_district_display(),
                'distance': round(r.distance.km, 1) if r.distance else None,
                'min_price': int(r.min_price) if r.min_price else None,
                'cheapest_dish_name': r.cheapest_dish_name,
                'image': get_restaurant_display_image(r),
                'lat': r.location.y,
                'lng': r.location.x
            })

        return JsonResponse(data, safe=False)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
def api_book_table(request):
    """
    API đặt bàn với các tính năng:
    - Chọn bàn theo số người
    - Chọn các món ăn (tùy chọn)
    - Kiểm tra bàn trống
    - Kiểm tra quy định không đặt sớm quá 90 phút
    - Hỗ trợ hàng chờ nếu bàn bận
    
    Expected POST parameters:
    - restaurant_id: ID nhà hàng
    - name: Tên khách hàng
    - phone: Số điện thoại (tùy chọn)
    - booking_time: Thời gian đặt (YYYY-MM-DD HH:MM hoặc ISO format)
    - people: Số người (mặc định 4)
    - dish_ids[]: Danh sách ID các món ăn (tùy chọn)
    - quantities[]: Số lượng từng món (tùy chọn)
    - note: Ghi chú (tùy chọn)
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Yêu cầu không hợp lệ'})

    try:
        restaurant_id = request.POST.get('restaurant_id')
        customer_name = request.POST.get('name', '').strip()
        customer_phone = request.POST.get('phone', '').strip()
        booking_time_str = request.POST.get('time') or request.POST.get('booking_time')
        people = int(request.POST.get('people', 4))
        note = request.POST.get('note', '').strip()

        # Validation
        if not customer_name:
            return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập tên khách hàng!'}, status=400)
        
        if people < 1 or people > 20:
            return JsonResponse({'status': 'error', 'message': 'Số người phải từ 1 đến 20!'}, status=400)

        # Lấy nhà hàng
        restaurant = Restaurant.objects.get(id=restaurant_id)

        # Tạo bàn mặc định nếu chưa có
        if not restaurant.tables.exists():
            create_default_tables_for_restaurant(restaurant)

        # Parse thời gian
        requested_time = parse_user_datetime(booking_time_str)
        if requested_time is None:
            return JsonResponse({'status': 'error', 'message': 'Thời gian đặt bàn không hợp lệ.'}, status=400)

        # ✅ Kiểm tra quy định 90 phút
        is_valid_time, error_msg = validate_booking_time(requested_time)
        if not is_valid_time:
            return JsonResponse({'status': 'error', 'message': error_msg}, status=400)

        # ✅ Tìm bàn trống phù hợp
        best_table, available_from = find_best_table_for_booking(
            restaurant=restaurant,
            people=people,
            requested_time=requested_time
        )

        if best_table is None:
            return JsonResponse({
                'status': 'error',
                'message': '❌ Không có bàn phù hợp với số lượng khách này. Vui lòng chọn thời gian khác!'
            }, status=400)

        # Kiểm tra có phải hàng chờ không
        is_waiting = available_from > requested_time
        queue_position = 0

        if is_waiting:
            queue_position = Reservation.objects.filter(
                table=best_table,
                booking_time=available_from,
                status='waiting'
            ).count() + 1

        # Tạo đơn đặt bàn
        reservation = Reservation(
            table=best_table,
            customer_name=customer_name,
            customer_phone=customer_phone,
            booking_time=available_from,
            number_of_people=people,
            note=note,
            status='waiting' if is_waiting else 'pending',
            queue_position=queue_position
        )

        if request.user.is_authenticated:
            reservation.user = request.user

        reservation.save()

        # ✅ Xử lý thêm các món ăn (ReservationItem)
        dish_ids = request.POST.getlist('dish_ids[]')
        quantities = request.POST.getlist('quantities[]')
        total_price = 0

        if dish_ids:
            for index, dish_id in enumerate(dish_ids):
                try:
                    qty = max(1, int(quantities[index])) if index < len(quantities) else 1
                except (ValueError, TypeError):
                    qty = 1

                # Lấy món ăn
                dish = Dish.objects.filter(
                    id=dish_id,
                    restaurant=restaurant,
                    is_available=True
                ).first()

                if dish:
                    # Tạo ReservationItem
                    reservation_item, created = ReservationItem.objects.get_or_create(
                        reservation=reservation,
                        dish=dish,
                        defaults={'quantity': qty}
                    )
                    if not created:
                        reservation_item.quantity = qty
                        reservation_item.save()
                    
                    total_price += dish.price * qty

        # Gửi email xác nhận (nếu có email)
        if customer_phone or (request.user.is_authenticated and request.user.email):
            try:
                send_booking_confirmation_email(reservation)
            except Exception as e:
                print(f"Lỗi gửi email đặt bàn: {e}")

        # Phản hồi thành công
        if is_waiting:
            message = (
                f"✅ Hiện đã hết bàn đúng giờ bạn chọn. "
                f"Bạn được đưa vào hàng chờ tại {best_table.table_number} "
                f"lúc {available_from.strftime('%d/%m/%Y %H:%M')}. "
                f"Số thứ tự chờ: {queue_position}."
            )
            booking_type = 'waiting'
        else:
            message = f"✅ Thành công! Đơn đặt tại {restaurant.name} đang chờ duyệt."
            booking_type = 'normal'

        return JsonResponse({
            'status': 'success',
            'booking_type': booking_type,
            'reservation_id': reservation.id,
            'message': message,
            'total_price': int(total_price),
            'items_count': len([d for d in dish_ids if d])
        })

    except Restaurant.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Nhà hàng không tồn tại!'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'❌ Lỗi server: {str(e)}'}, status=500)


@csrf_exempt
def api_pickup_order(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Yêu cầu không hợp lệ'})

    try:
        restaurant_id = request.POST.get('restaurant_id')
        customer_name = request.POST.get('customer_name')
        customer_phone = request.POST.get('customer_phone')
        pickup_time_str = request.POST.get('pickup_time')
        note = request.POST.get('note', '').strip()

        restaurant = Restaurant.objects.get(id=restaurant_id)

        if not restaurant.is_pickup_available:
            return JsonResponse({
                'status': 'error',
                'message': 'Quán này chưa bật chức năng đặt trước đến lấy món.'
            })

        pickup_time = parse_user_datetime(pickup_time_str)
        if pickup_time is None:
            return JsonResponse({'status': 'error', 'message': 'Thời gian lấy món không hợp lệ.'})

        order = PickupOrder.objects.create(
            restaurant=restaurant,
            customer_name=customer_name,
            customer_phone=customer_phone,
            pickup_time=pickup_time,
            note=note,
            status='pending',
            user=request.user if request.user.is_authenticated else None
        )

        dish_ids = request.POST.getlist('dish_ids[]')
        quantities = request.POST.getlist('quantities[]')

        if not dish_ids:
            order.delete()
            return JsonResponse({'status': 'error', 'message': 'Bạn chưa chọn món nào để đặt trước.'})

        created_items = 0
        for index, dish_id in enumerate(dish_ids):
            try:
                qty = max(1, int(quantities[index])) if index < len(quantities) else 1
            except (ValueError, TypeError):
                qty = 1

            dish = Dish.objects.filter(
                id=dish_id,
                restaurant=restaurant,
                is_available=True
            ).first()

            if dish:
                PickupOrderItem.objects.create(
                    pickup_order=order,
                    dish=dish,
                    quantity=qty
                )
                created_items += 1

        if created_items == 0:
            order.delete()
            return JsonResponse({'status': 'error', 'message': 'Không có món hợp lệ trong đơn đặt trước.'})

        return JsonResponse({
            'status': 'success',
            'message': (
                f'Đặt trước thành công! '
                f'Bạn vui lòng đến {restaurant.name} lúc {pickup_time.strftime("%d/%m/%Y %H:%M")} để nhận món.'
            )
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': 'Lỗi server: ' + str(e)})


# PHẦN 4: ADMIN DASHBOARD & MANAGEMENT

@user_passes_test(lambda u: u.is_superuser)
def admin_dashboard(request):
    context = {
        'total_restaurants': Restaurant.objects.count(),
        'total_reservations': Reservation.objects.count(),
        'total_tables': Table.objects.count(),
        'active_page': 'dashboard'
    }
    return render(request, 'restaurants/admin_dashboard.html', context)


@user_passes_test(lambda u: u.is_superuser)
def admin_restaurant_list(request):
    restaurants = Restaurant.objects.prefetch_related('gallery_images').all().order_by('-created_at')
    for restaurant in restaurants:
        restaurant.display_image_url = get_restaurant_display_image(restaurant)

    context = {
        'restaurants': restaurants,
        'active_page': 'restaurants'
    }
    return render(request, 'restaurants/admin_manage.html', context)


@user_passes_test(lambda u: u.is_superuser)
def admin_restaurant_form(request, pk=None):
    if pk:
        restaurant = get_object_or_404(Restaurant.objects.prefetch_related('gallery_images'), pk=pk)
        action_title = "CẬP NHẬT QUÁN ĂN"
    else:
        restaurant = None
        action_title = "THÊM QUÁN MỚI"

    if request.method == "POST":
        name = request.POST.get('name')
        address = request.POST.get('address')
        district = request.POST.get('district')
        image = request.FILES.get('image')
        gallery_images = request.FILES.getlist('gallery_images')
        is_pickup_available = request.POST.get('is_pickup_available') == 'on'

        lat = float(request.POST.get('lat'))
        lng = float(request.POST.get('lng'))
        pnt = Point(lng, lat, srid=4326)

        if restaurant:
            restaurant.name = name
            restaurant.address = address
            restaurant.district = district
            restaurant.location = pnt
            restaurant.is_pickup_available = is_pickup_available
            if image:
                restaurant.image = image
            restaurant.save()

            if not restaurant.tables.exists():
                create_default_tables_for_restaurant(restaurant)

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
                image=image,
                is_pickup_available=is_pickup_available
            )

            create_default_tables_for_restaurant(restaurant)

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


@user_passes_test(lambda u: u.is_superuser)
def admin_menu_list(request, pk):
    restaurant = get_object_or_404(Restaurant, pk=pk)
    dishes = restaurant.dishes.all()
    return render(request, 'restaurants/admin_menu_list.html', {'restaurant': restaurant, 'dishes': dishes})


@login_required(login_url='login')
@user_passes_test(lambda u: u.is_superuser)
def admin_import_dishes(request, pk):
    """
    View để import dữ liệu các món ăn từ file Excel
    """
    restaurant = get_object_or_404(Restaurant, pk=pk)
    
    context = {
        'restaurant': restaurant,
        'form': DishImportForm(),
    }
    
    if request.method == 'POST':
        form = DishImportForm(request.POST, request.FILES)
        
        if form.is_valid():
            excel_file = request.FILES['excel_file']
            
            # Xử lý import
            handler = DishImportHandler(excel_file, restaurant)
            result = handler.import_dishes()
            
            # Thêm thông báo
            if result['errors']:
                for error in result['errors']:
                    flash_msg.error(request, error)
            
            if result['warnings']:
                for warning in result['warnings']:
                    flash_msg.warning(request, warning)
            
            if result['success_count'] > 0:
                flash_msg.success(request, result['message'])
                return redirect('admin_menu_list', pk=pk)
        else:
            for error in form.errors.values():
                flash_msg.error(request, str(error))
        
        context['form'] = form
    
    return render(request, 'restaurants/admin_import_dishes.html', context)


@login_required(login_url='login')
@user_passes_test(lambda u: u.is_superuser)
def download_sample_dishes_template(request, pk):
    """
    View để tải file Excel mẫu để import dữ liệu các món ăn
    """
    from io import BytesIO
    from django.http import HttpResponse
    
    restaurant = get_object_or_404(Restaurant, pk=pk)

    try:
        # Tạo file Excel trong bộ nhớ
        from .import_dishes_from_excel import create_sample_excel_template
        
        # Tạo BytesIO object để lưu file
        excel_buffer = BytesIO()
        
        # Tạo file Excel
        create_sample_excel_template(excel_buffer)
        excel_buffer.seek(0)
        
        # Trả file về client
        response = HttpResponse(
            excel_buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="Mau_nhap_mon_an_{restaurant.name.replace(" ", "_")}.xlsx"'
        
        return response
    
    except Exception as e:
        flash_msg.error(request, f"❌ Lỗi tạo file mẫu: {str(e)}")
        return redirect('admin_menu_list', pk=pk)


@login_required(login_url='login')
@user_passes_test(lambda u: u.is_superuser)
def admin_dish_form(request, pk):
    restaurant = get_object_or_404(Restaurant, pk=pk)

    if request.method == "POST":
        is_price_representative = request.POST.get('is_price_representative') == 'on'

        if is_price_representative:
            Dish.objects.filter(restaurant=restaurant).update(is_price_representative=False)

        Dish.objects.create(
            restaurant=restaurant,
            name=request.POST.get('name'),
            price=request.POST.get('price'),
            description=request.POST.get('description'),
            image=request.FILES.get('image'),
            is_available=request.POST.get('is_available') == 'on',
            is_price_representative=is_price_representative
        )
        flash_msg.success(request, "Đã thêm món mới!")
        return redirect('admin_menu_list', pk=pk)

    return render(request, 'restaurants/admin_dish_form.html', {
        'restaurant': restaurant,
        'action': 'Thêm'
    })


@user_passes_test(lambda u: u.is_superuser)
def admin_dish_edit(request, dish_id):
    dish = get_object_or_404(Dish, pk=dish_id)
    restaurant = dish.restaurant

    if request.method == "POST":
        is_price_representative = request.POST.get('is_price_representative') == 'on'

        if is_price_representative:
            Dish.objects.filter(restaurant=restaurant).update(is_price_representative=False)

        dish.name = request.POST.get('name')
        dish.price = request.POST.get('price')
        dish.description = request.POST.get('description')
        if request.FILES.get('image'):
            dish.image = request.FILES.get('image')
        dish.is_available = request.POST.get('is_available') == 'on'
        dish.is_price_representative = is_price_representative
        dish.save()

        flash_msg.success(request, "Cập nhật món thành công!")
        return redirect('admin_menu_list', pk=restaurant.pk)

    return render(request, 'restaurants/admin_dish_form.html', {
        'restaurant': restaurant,
        'dish': dish,
        'action': 'Sửa'
    })


@user_passes_test(lambda u: u.is_superuser)
def admin_dish_delete(request, dish_id):
    dish = get_object_or_404(Dish, pk=dish_id)
    restaurant_id = dish.restaurant.pk
    dish.delete()
    flash_msg.warning(request, "Đã xóa món ăn!")
    return redirect('admin_menu_list', pk=restaurant_id)


@user_passes_test(lambda u: u.is_superuser)
def admin_booking_list(request, pk):
    restaurant = get_object_or_404(Restaurant, pk=pk)
    bookings = Reservation.objects.filter(
        table__restaurant=restaurant
    ).order_by('-booking_time')
    return render(request, 'restaurants/admin_booking_list.html', {'restaurant': restaurant, 'bookings': bookings})


@user_passes_test(lambda u: u.is_superuser)
def admin_all_bookings(request):
    bookings = Reservation.objects.all().select_related('table__restaurant').order_by('-booking_time')

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
    booking = get_object_or_404(Reservation, pk=booking_id)

    if status in ['confirmed', 'cancelled', 'pending', 'waiting', 'completed']:
        booking.status = status
        booking.save()
        flash_msg.success(request, f"Đã cập nhật trạng thái đơn của {booking.customer_name} thành công!")
    else:
        flash_msg.error(request, "Trạng thái không hợp lệ!")

    return redirect('admin_booking_list', pk=booking.table.restaurant.pk)


def feedback_form(request, pk):
    restaurant = get_object_or_404(Restaurant, pk=pk)

    if request.method == 'POST':
        customer_name = request.POST.get('customer_name', '').strip()
        customer_email = request.POST.get('customer_email', '').strip().lower()
        rating = request.POST.get('rating')
        message = request.POST.get('message', '').strip()

        if Feedback.objects.filter(restaurant=restaurant, customer_email__iexact=customer_email).exists():
            flash_msg.error(request, "Email này đã đánh giá quán này rồi. Mỗi email chỉ được đánh giá 1 lần.")
            return redirect('feedback_form', pk=pk)

        feedback = Feedback.objects.create(
            restaurant=restaurant,
            customer_name=customer_name,
            customer_email=customer_email,
            rating=rating,
            message=message
        )

        try:
            send_feedback_email_to_admin(feedback)
        except Exception as e:
            print(f"Lỗi gửi email admin: {e}")

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
    feedbacks = Feedback.objects.all().select_related('restaurant').order_by('-created_at')

    restaurant_id = request.GET.get('restaurant_id')
    restaurant_name = None
    if restaurant_id:
        feedbacks = feedbacks.filter(restaurant_id=restaurant_id)
        restaurant_name = Restaurant.objects.get(id=restaurant_id).name

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
    feedback = get_object_or_404(Feedback, pk=feedback_id)
    feedback.is_read = True
    feedback.save()
    flash_msg.success(request, "Đã đánh dấu phản hồi này là đã xem.")
    return redirect('admin_feedback_list', pk=feedback.restaurant.pk)


def send_feedback_email_to_admin(feedback):
    subject = f"🔔 Phản hồi mới từ {feedback.customer_name} - {feedback.restaurant.name}"

    html_message = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #dc3545; color: white; padding: 20px; text-align: center;">
                    <h2 style="margin: 0;">📝 Phản hồi từ khách hàng</h2>
                </div>

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

                    <div style="text-align: center; margin: 20px 0;">
                        <a href="http://localhost:8000/my-admin/restaurant/{feedback.restaurant.id}/feedbacks/"
                           style="background-color: #dc3545; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                            👁️ Xem chi tiết
                        </a>
                    </div>
                </div>

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
    subject = "✅ Phản hồi của bạn đã được nhận"

    html_message = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #28a745; color: white; padding: 20px; text-align: center;">
                    <h2 style="margin: 0;">✅ Cảm ơn bạn!</h2>
                </div>

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


def send_booking_confirmation_email(reservation):
    """Gửi email xác nhận đặt bàn cho khách hàng"""
    subject = f"✅ Xác nhận đặt bàn - {reservation.table.restaurant.name}"
    
    # Lấy danh sách các món đã chọn
    items_html = ""
    if reservation.items.exists():
        items_html = "<h4>Các món đã chọn:</h4><div style='background-color: #f5f5f5; padding: 15px; border-radius: 4px;'><table style='width: 100%;'>"
        items_html += "<tr style='border-bottom: 1px solid #ddd;'><th style='text-align: left; padding: 5px;'>Món ăn</th><th style='text-align: center; padding: 5px;'>SL</th><th style='text-align: right; padding: 5px;'>Giá</th></tr>"
        
        total_price = 0
        for item in reservation.items.all():
            subtotal = item.quantity * item.dish.price
            total_price += subtotal
            items_html += f"<tr style='border-bottom: 1px solid #eee;'>"
            items_html += f"<td style='padding: 8px;'>{item.dish.name}</td>"
            items_html += f"<td style='text-align: center; padding: 8px;'>{item.quantity}</td>"
            items_html += f"<td style='text-align: right; padding: 8px;'>{int(subtotal):,} ₫</td>"
            items_html += f"</tr>"
        
        items_html += f"<tr style='font-weight: bold;'><td colspan='2' style='text-align: right; padding: 10px;'>Tổng cộng:</td><td style='text-align: right; padding: 10px;'>{int(total_price):,} ₫</td></tr>"
        items_html += "</table></div>"

    status_text = "🔄 Hàng chờ" if reservation.status == 'waiting' else "⏳ Chờ duyệt"
    
    html_message = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #007bff; color: white; padding: 20px; text-align: center;">
                    <h2 style="margin: 0;">✅ Đơn đặt bàn của bạn</h2>
                </div>

                <div style="padding: 20px;">
                    <p>Xin chào <strong>{reservation.customer_name}</strong>,</p>
                    <p>Cảm ơn bạn đã đặt bàn tại quán ăn <strong>{reservation.table.restaurant.name}</strong>!</p>

                    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">

                    <h4>📋 Thông tin đặt bàn:</h4>
                    <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #007bff; border-radius: 4px;">
                        <p><strong>Quán ăn:</strong> {reservation.table.restaurant.name}</p>
                        <p><strong>Bàn:</strong> {reservation.table.table_number}</p>
                        <p><strong>Thời gian:</strong> {reservation.booking_time.strftime('%d/%m/%Y %H:%M')}</p>
                        <p><strong>Số người:</strong> {reservation.number_of_people} người</p>
                        <p><strong>Trạng thái:</strong> {status_text}</p>
                        <p><strong>Mã đơn:</strong> #{reservation.id}</p>
                        {f'<p><strong>Vị trí hàng chờ:</strong> #{reservation.queue_position}</p>' if reservation.status == 'waiting' else ''}
                    </div>

                    {items_html}

                    {f'<p style="color: #dc3545; font-weight: bold;">💡 Bạn đang ở hàng chờ. Chúng tôi sẽ thông báo cho bạn khi có bàn trống.</p>' if reservation.status == 'waiting' else ''}

                    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">

                    <p style="color: #666; font-size: 14px;">
                        Nếu bạn cần thay đổi hoặc hủy đặt bàn, vui lòng liên hệ với chúng tôi sớm nhất.
                    </p>

                    <div style="text-align: center; margin: 20px 0;">
                        <p style="color: #999; font-size: 13px;">
                            Địa chỉ: {reservation.table.restaurant.address}<br>
                            Quận/Huyện: {reservation.table.restaurant.get_district_display()}
                        </p>
                    </div>
                </div>

                <div style="background-color: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; color: #666;">
                    <p>GIS Eatery © 2026 | Hệ thống quản lý quán ăn</p>
                    <p>Email này được gửi tự động, vui lòng không trả lời email này.</p>
                </div>
            </div>
        </body>
    </html>
    """

    plain_message = strip_tags(html_message)
    
    # Lấy email khách hàng
    recipient_email = None
    if reservation.user and reservation.user.email:
        recipient_email = reservation.user.email
    
    # Chỉ gửi email nếu có email hợp lệ
    if recipient_email:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email='noreply@giseatery.com',
            recipient_list=[recipient_email],
            html_message=html_message,
            fail_silently=False,
        )


@csrf_exempt
@require_GET
def api_geocode_address(request):
    query = request.GET.get('q', '').strip()

    if not query:
        return JsonResponse({'error': 'Thiếu địa chỉ cần tìm'}, status=400)

    try:
        response = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={
                'format': 'jsonv2',
                'q': query,
                'limit': 5,
                'accept-language': 'vi',
                'countrycodes': 'vn',
                'addressdetails': 1
            },
            headers={
                'User-Agent': 'GIS_Eatery/1.0'
            },
            timeout=10
        )
        response.raise_for_status()
        
        # Lấy kết quả đầu tiên và trả về lat, lng
        results = response.json()
        if results:
            first_result = results[0]
            return JsonResponse({
                'lat': float(first_result.get('lat')),
                'lng': float(first_result.get('lon')),
                'address': first_result.get('display_name', query)
            })
        else:
            return JsonResponse({'error': 'Không tìm thấy địa chỉ'}, status=404)

    except requests.RequestException as e:
        return JsonResponse({'error': f'Lỗi geocoding: {str(e)}'}, status=500)


@csrf_exempt
@require_GET
def api_reverse_geocode_address(request):
    """Chuyển đổi tọa độ (lat, lng) → địa chỉ (reverse geocoding)"""
    lat = request.GET.get('lat', '').strip()
    lng = request.GET.get('lng', '').strip()

    if not lat or not lng:
        return JsonResponse({'error': 'Thiếu tọa độ (lat, lng)'}, status=400)

    try:
        lat = float(lat)
        lng = float(lng)
    except ValueError:
        return JsonResponse({'error': 'Tọa độ không hợp lệ'}, status=400)

    try:
        response = requests.get(
            'https://nominatim.openstreetmap.org/reverse',
            params={
                'format': 'jsonv2',
                'lat': lat,
                'lon': lng,
                'accept-language': 'vi',
                'addressdetails': 1,
                'zoom': 18
            },
            headers={
                'User-Agent': 'GIS_Eatery/1.0'
            },
            timeout=10
        )
        response.raise_for_status()
        return JsonResponse(response.json())

    except requests.RequestException as e:
        return JsonResponse({'error': f'Lỗi reverse geocoding: {str(e)}'}, status=500)