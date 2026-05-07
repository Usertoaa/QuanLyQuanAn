import requests
from datetime import datetime, timedelta
import uuid
import hashlib
import os
from django.http import FileResponse
from io import BytesIO

from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.contrib.gis.geos import Point
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.db.models import Q, OuterRef, Subquery, Count
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
from django.db import IntegrityError, transaction

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
    AmenityCategory,
    RestaurantAmenity,
)
from .forms import CustomUserCreationForm, CustomSetPasswordForm, DishImportForm
from .import_dishes_from_excel import DishImportHandler
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ============================================
# CONSTANTS
# ============================================
BOOKING_DURATION_MINUTES = 90
AUTO_CANCEL_AFTER_MINUTES = 30
ACTIVE_RESERVATION_STATUSES = ['pending', 'confirmed', 'waiting']
STANDARD_TABLE_LAYOUT = [
    ('Bàn 1', 4),
    ('Bàn 2', 4),
    ('Bàn 3', 4),
    ('Bàn 4', 4),
    ('Bàn 5', 10),
    ('Bàn 6', 10),
]
STANDARD_TABLE_NUMBERS = [item[0] for item in STANDARD_TABLE_LAYOUT]
AMENITY_ICON_PRESETS = [
    {'icon': 'fas fa-wifi', 'label': 'Wifi'},
    {'icon': 'fas fa-snowflake', 'label': 'May lanh'},
    {'icon': 'fas fa-parking', 'label': 'Gui xe'},
    {'icon': 'fas fa-fan', 'label': 'Hut khoi'},
    {'icon': 'fas fa-restroom', 'label': 'Toilet'},
    {'icon': 'fas fa-calendar-check', 'label': 'Dat ban'},
    {'icon': 'fas fa-motorcycle', 'label': 'Giao hang'},
    {'icon': 'fas fa-chair', 'label': 'Ban cao'},
    {'icon': 'fas fa-music', 'label': 'Nhac song'},
    {'icon': 'fas fa-truck', 'label': 'Van chuyen'},
    {'icon': 'fas fa-credit-card', 'label': 'Thanh toan'},
    {'icon': 'fas fa-tv', 'label': 'Tivi'},
    {'icon': 'fas fa-plug', 'label': 'O cam'},
    {'icon': 'fas fa-clock', 'label': 'Mo cua khuya'},
    {'icon': 'fas fa-couch', 'label': 'Sofa'},
]
DEFAULT_AMENITY_CATEGORIES = [
    {
        'name': 'Free Wifi',
        'icon': 'fas fa-wifi',
        'description': 'Wifi mien phi cho khach hang.',
        'order': 1,
    },
    {
        'name': 'Máy lạnh',
        'icon': 'fas fa-snowflake',
        'description': 'Khu vuc co may lanh.',
        'order': 2,
    },
    {
        'name': 'Giữ xe',
        'icon': 'fas fa-parking',
        'description': 'Co cho gui xe cho khach.',
        'order': 3,
    },
    {
        'name': 'Bàn hút khói',
        'icon': 'fas fa-fan',
        'description': 'Co khu vuc danh cho khach hut thuoc.',
        'order': 4,
    },
    {
        'name': 'Toilet sạch',
        'icon': 'fas fa-restroom',
        'description': 'Nha ve sinh sach se.',
        'order': 5,
    },
    {
        'name': 'Đặt bàn trước',
        'icon': 'fas fa-calendar-check',
        'description': 'Nhan dat ban truoc.',
        'order': 6,
    },
    {
        'name': 'Giao hàng',
        'icon': 'fas fa-motorcycle',
        'description': 'Ho tro giao hang.',
        'order': 7,
    },
    {
        'name': 'Có bàn cao',
        'icon': 'fas fa-chair',
        'description': 'Co ban cao de ngoi lam viec.',
        'order': 8,
    },
    {
        'name': 'Nhạc sống',
        'icon': 'fas fa-music',
        'description': 'Co chuong trinh nhac song.',
        'order': 9,
    },
]


# ============================================
# UTILITY FUNCTIONS - BOOKING & TIME
# ============================================

def validate_booking_time(requested_time):
    """
    Kiểm tra thời gian đặt bàn có hợp lệ không
    - Không được đặt ở quá khứ
    
    Returns: (is_valid, error_message)
    """
    now = timezone.now()
    
    # Kiểm tra thời gian đặt ở quá khứ
    if requested_time < now:
        return False, "⚠️ Thời gian đặt không thể ở quá khứ!"
    
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
    existing_tables = {
        table.table_number: table
        for table in restaurant.tables.all()
    }
    tables_to_create = []
    tables_to_update = []

    for table_number, capacity in STANDARD_TABLE_LAYOUT:
        table = existing_tables.get(table_number)
        if table is None:
            tables_to_create.append(
                Table(
                    restaurant=restaurant,
                    table_number=table_number,
                    capacity=capacity,
                    is_available=True,
                )
            )
            continue

        should_update = False
        if table.capacity != capacity:
            table.capacity = capacity
            should_update = True

        if should_update:
            tables_to_update.append(table)

    if tables_to_create:
        Table.objects.bulk_create(tables_to_create)
    if tables_to_update:
        Table.objects.bulk_update(tables_to_update, ['capacity'])


def ensure_default_amenity_categories():
    existing_names = set(
        AmenityCategory.objects.filter(
            name__in=[item['name'] for item in DEFAULT_AMENITY_CATEGORIES]
        ).values_list('name', flat=True)
    )

    missing_categories = [
        AmenityCategory(**item)
        for item in DEFAULT_AMENITY_CATEGORIES
        if item['name'] not in existing_names
    ]
    if missing_categories:
        AmenityCategory.objects.bulk_create(missing_categories)


def expire_overdue_reservations(restaurant=None):
    expired_before = timezone.now() - timedelta(minutes=AUTO_CANCEL_AFTER_MINUTES)
    expired_qs = Reservation.objects.filter(
        status__in=ACTIVE_RESERVATION_STATUSES,
        booking_time__lt=expired_before,
    )
    if restaurant is not None:
        expired_qs = expired_qs.filter(table__restaurant=restaurant)

    return expired_qs.update(status='cancelled', queue_position=0)


def is_table_available_for_booking(table, requested_time):
    requested_end_time = requested_time + timedelta(minutes=BOOKING_DURATION_MINUTES)
    earliest_possible_overlap = requested_time - timedelta(minutes=BOOKING_DURATION_MINUTES)

    candidate_reservations = Reservation.objects.filter(
        table=table,
        status__in=ACTIVE_RESERVATION_STATUSES,
        booking_time__lt=requested_end_time,
        booking_time__gt=earliest_possible_overlap,
    ).only('booking_time')

    for reservation in candidate_reservations:
        existing_start = reservation.booking_time
        existing_end = existing_start + timedelta(minutes=BOOKING_DURATION_MINUTES)
        if requested_time < existing_end and existing_start < requested_end_time:
            return False

    return True


def find_available_table_for_booking(restaurant, people, requested_time):
    candidate_tables = restaurant.tables.filter(
        table_number__in=STANDARD_TABLE_NUMBERS,
        is_available=True,
        capacity__gte=people
    ).order_by('capacity', 'id')

    for table in candidate_tables:
        if is_table_available_for_booking(table, requested_time):
            return table

    return None


# ============================================
# PUBLIC VIEWS - USER INTERFACE
# ============================================

def index(request):
    ensure_default_amenity_categories()

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

    # ============================================
    # AMENITY FILTER
    # ============================================
    amenity_ids = request.GET.getlist('amenities')
    if amenity_ids:
        restaurants = restaurants.filter(
            amenities__category_id__in=amenity_ids,
            amenities__is_available=True
        ).distinct()

    for restaurant in restaurants:
        restaurant.display_image_url = get_restaurant_display_image(restaurant)

    # Prepare amenities data as JSON for JavaScript
    amenities_json = list(AmenityCategory.objects.all().order_by('order').values('id', 'name', 'icon'))
    
    import json
    context = {
        'restaurants': restaurants,
        'districts': districts,
        'current_district': district_filter,
        'current_sort': sort,
        'amenity_categories': AmenityCategory.objects.all().order_by('order'),
        'amenities_json': json.dumps(amenities_json),
        'selected_amenities': amenity_ids,
    }
    return render(request, 'restaurants/index.html', context)


def about_page(request):
    context = {
        'total_restaurants': Restaurant.objects.count(),
        'total_dishes': Dish.objects.count(),
        'total_feedbacks': Feedback.objects.count(),
        'total_users': User.objects.filter(is_active=True).count(),
        'total_reservations': Reservation.objects.count(),
    }
    return render(request, 'restaurants/about.html', context)


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
    get_object_or_404(Restaurant, pk=pk)
    return redirect(f"{reverse('user_map')}?restaurant_id={pk}&auto_route=1")


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
            request.session['pending_verification_email'] = user.email
            
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
        settings.DEFAULT_FROM_EMAIL,
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
    context = {
        'pending_email': request.session.get('pending_verification_email', ''),
        'is_console_email_backend': settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend',
        'is_file_email_backend': settings.EMAIL_BACKEND == 'django.core.mail.backends.filebased.EmailBackend',
    }
    return render(request, 'restaurants/verification_pending.html', context)


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
            
            # Lưu email vào session để hiển thị ở trang success
            request.session['reset_email'] = user.email
            return redirect('forgot_password_success')
        
        except User.DoesNotExist:
            # Không tiết lộ rằng email không tồn tại (bảo mật)
            # Nhưng vẫn redirect đến trang success để tránh reveal email
            return redirect('forgot_password_success')
    
    return render(request, 'restaurants/forgot_password.html')


def forgot_password_success(request):
    """
    Trang thông báo sau khi gửi email reset
    """
    email = request.session.get('reset_email', '')
    if not email:
        return redirect('forgot_password')
    
    # Xóa email khỏi session
    if 'reset_email' in request.session:
        del request.session['reset_email']
    
    return render(request, 'restaurants/forgot_password_success.html', {'email': email})


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
    expire_overdue_reservations()

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


def api_export_nearby_excel(request):
    """
    Xuất file Excel theo bán kính được chọn trên giao diện bản đồ
    (giới hạn tối đa 15km), kèm toàn bộ món ăn của các quán trong bán kính đó.
    """
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Thiếu hoặc sai định dạng tọa độ lat/lng'}, status=400)
    raw_radius = (request.GET.get('radius') or '').strip()
    if not raw_radius:
        raw_radius = (request.GET.get('radii') or '').split(',')[0].strip()

    try:
        radius = float(raw_radius) if raw_radius else 5.0
    except ValueError:
        radius = 5.0

    if radius <= 0:
        radius = 5.0

    max_export_radius = 15.0
    if radius > max_export_radius:
        radius = max_export_radius

    radius = round(radius, 2)
    radius_label = f'{radius:g}'.replace('.', '_')
    user_location = Point(lng, lat, srid=4326)

    workbook = Workbook()
    summary_sheet = workbook.active
    summary_sheet.title = 'Tong_quan'

    # =========================
    # Excel styles
    # =========================
    header_fill = PatternFill(start_color='CF2127', end_color='CF2127', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True, size=11)
    title_font = Font(color='CF2127', bold=True, size=13)
    content_font = Font(size=10)
    center_align = Alignment(horizontal='center', vertical='center')
    left_align = Alignment(horizontal='left', vertical='top', wrap_text=True)
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9'),
    )

    restaurants = list(
        Restaurant.objects.prefetch_related('dishes').filter(
            location__distance_lte=(user_location, D(km=radius))
        ).annotate(
            distance=Distance('location', user_location)
        ).order_by('distance', 'name')
    )
    restaurant_dishes_map = {
        restaurant.id: list(restaurant.dishes.all().order_by('name'))
        for restaurant in restaurants
    }
    total_dishes_in_radius = sum(len(dishes) for dishes in restaurant_dishes_map.values())

    # =========================
    # Sheet 1: Tổng quan
    # =========================
    summary_sheet.merge_cells('A1:B1')
    summary_sheet['A1'] = 'BÁO CÁO DANH SÁCH QUÁN ĂN'
    summary_sheet['A1'].font = title_font
    summary_sheet['A1'].alignment = center_align

    summary_sheet.append(['Thông tin', 'Giá trị'])
    summary_sheet.append(['Vị trí tham chiếu', f'{lat:.6f}, {lng:.6f}'])
    summary_sheet.append(['Bán kính xuất', f'{radius:g} km'])
    summary_sheet.append(['Thời gian xuất', timezone.localtime().strftime('%d/%m/%Y %H:%M:%S')])
    summary_sheet.append([f'Kết quả trong {radius:g} km', f'{len(restaurants)} quán, {total_dishes_in_radius} món'])

    summary_sheet.column_dimensions['A'].width = 28
    summary_sheet.column_dimensions['B'].width = 45

    for cell in summary_sheet[2]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = thin_border

    for row in summary_sheet.iter_rows(min_row=3, max_row=6, min_col=1, max_col=2):
        for cell in row:
            cell.font = content_font
            cell.alignment = left_align
            cell.border = thin_border

    # =========================
    # Sheet 2: Bảng đẹp theo cột
    # =========================
    restaurant_sheet = workbook.create_sheet(title=f'{radius_label}km_quan')
    restaurant_sheet.append([
        'STT',
        'Tên quán',
        'Địa chỉ',
        'Quận/Huyện',
        'Khoảng cách (km)',
        'Số món',
        'Các món ăn',
    ])

    if not restaurants:
        restaurant_sheet.append([
            '',
            'Không có quán ăn trong bán kính này',
            '',
            '',
            '',
            '',
            '',
        ])
    else:
        for index, restaurant in enumerate(restaurants, start=1):
            dishes = restaurant_dishes_map.get(restaurant.id, [])
            dish_lines = []
            for dish in dishes:
                dish_price = f"{int(dish.price):,}đ" if dish.price is not None else 'Chưa cập nhật giá'
                dish_status = 'Còn bán' if dish.is_available else 'Tạm ngưng'
                dish_lines.append(f"- {dish.name} ({dish_price}, {dish_status})")

            restaurant_sheet.append([
                index,
                restaurant.name,
                restaurant.address,
                restaurant.get_district_display(),
                round(restaurant.distance.km, 2) if restaurant.distance else '',
                len(dishes),
                '\n'.join(dish_lines) if dish_lines else '(Quán chưa có món ăn)',
            ])

    # Style header
    for cell in restaurant_sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = thin_border

    # Style content
    for row in restaurant_sheet.iter_rows(min_row=2, max_row=restaurant_sheet.max_row, min_col=1, max_col=7):
        for cell in row:
            cell.font = content_font
            cell.alignment = left_align
            cell.border = thin_border

    # Đặt chiều rộng cột đẹp và dễ đọc
    preferred_widths = {
        1: 8,   # STT
        2: 30,  # Tên quán
        3: 45,  # Địa chỉ
        4: 16,  # Quận/Huyện
        5: 16,  # Khoảng cách
        6: 10,  # Số món
        7: 78,  # Các món ăn
    }
    for col_idx, width in preferred_widths.items():
        restaurant_sheet.column_dimensions[get_column_letter(col_idx)].width = width

    # Chiều cao dòng tự nhiên hơn cho cột "Các món ăn"
    for row_idx in range(2, restaurant_sheet.max_row + 1):
        dish_text = restaurant_sheet.cell(row=row_idx, column=7).value or ''
        line_count = max(1, len(str(dish_text).split('\n')))
        restaurant_sheet.row_dimensions[row_idx].height = min(180, 20 + (line_count - 1) * 15)

    excel_buffer = BytesIO()
    workbook.save(excel_buffer)
    excel_buffer.seek(0)

    response = HttpResponse(
        excel_buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f'danh_sach_quan_an_{timezone.localtime().strftime("%Y%m%d_%H%M%S")}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@csrf_exempt
def api_book_table(request):
    """
    API đặt bàn:
    - Chuẩn hóa số bàn mặc định theo từng quán
    - Khóa bàn trong 30 phút theo thời gian đặt
    - Tự hủy các đơn quá hạn 30 phút để giải phóng bàn
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

        if not customer_name:
            return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập tên khách hàng!'}, status=400)

        if people < 1 or people > 20:
            return JsonResponse({'status': 'error', 'message': 'Số người phải từ 1 đến 20!'}, status=400)

        restaurant = Restaurant.objects.get(id=restaurant_id)

        # Đảm bảo layout bàn tiêu chuẩn: 4 bàn 4 ghế + 2 bàn 10 ghế.
        create_default_tables_for_restaurant(restaurant)

        requested_time = parse_user_datetime(booking_time_str)
        if requested_time is None:
            return JsonResponse({'status': 'error', 'message': 'Thời gian đặt bàn không hợp lệ.'}, status=400)

        is_valid_time, error_msg = validate_booking_time(requested_time)
        if not is_valid_time:
            return JsonResponse({'status': 'error', 'message': error_msg}, status=400)

        # Tự động hủy các đơn quá hạn 30 phút trước khi tìm bàn trống.
        expire_overdue_reservations(restaurant)

        requested_end_time = requested_time + timedelta(minutes=BOOKING_DURATION_MINUTES)

        candidate_tables = list(
            restaurant.tables.filter(
                table_number__in=STANDARD_TABLE_NUMBERS,
                is_available=True,
                capacity__gte=people
            ).order_by('capacity', 'id')
        )

        available_tables = [
            table for table in candidate_tables
            if is_table_available_for_booking(table, requested_time)
        ]

        if not available_tables:
            return JsonResponse({
                'status': 'error',
                'message': 'Hết bàn trong khung giờ này. Vui lòng chọn giờ khác!'
            }, status=400)

        table = available_tables[0]

        reservation = Reservation(
            table=table,
            customer_name=customer_name,
            customer_phone=customer_phone,
            booking_time=requested_time,
            number_of_people=people,
            note=note,
            status='pending',
            queue_position=0,
        )

        if request.user.is_authenticated:
            reservation.user = request.user

        reservation.save()

        dish_ids = request.POST.getlist('dish_ids[]')
        quantities = request.POST.getlist('quantities[]')
        total_price = 0

        if dish_ids:
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
                    reservation_item, created = ReservationItem.objects.get_or_create(
                        reservation=reservation,
                        dish=dish,
                        defaults={'quantity': qty}
                    )
                    if not created:
                        reservation_item.quantity = qty
                        reservation_item.save()

                    total_price += dish.price * qty

        if customer_phone or (request.user.is_authenticated and request.user.email):
            try:
                send_booking_confirmation_email(reservation)
            except Exception as e:
                print(f'Lỗi gửi email đặt bàn: {e}')

        return JsonResponse({
            'status': 'success',
            'booking_type': 'normal',
            'reservation_id': reservation.id,
            'message': (
                f'Đặt bàn thành công tại {restaurant.name}. '
                f'Khung giờ của bạn: {requested_time.strftime("%H:%M")} - {requested_end_time.strftime("%H:%M")} '
                f'({BOOKING_DURATION_MINUTES} phút).'
            ),
            'total_price': int(total_price),
            'items_count': len([d for d in dish_ids if d]),
            'table_number': table.table_number,
            'booking_end_time': requested_end_time.isoformat(),
        })

    except Restaurant.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Nhà hàng không tồn tại!'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Lỗi server: {str(e)}'}, status=500)


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
def admin_user_accounts(request):
    query = (request.GET.get('q') or '').strip()
    status_filter = (request.GET.get('status') or 'all').strip()

    users = User.objects.annotate(
        booking_count=Count('reservations', distinct=True)
    ).order_by('-date_joined')

    if query:
        users = users.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )

    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    elif status_filter == 'verified':
        users = users.filter(profile__email_verified=True)
    elif status_filter == 'unverified':
        users = users.exclude(profile__email_verified=True)
    elif status_filter == 'admin':
        users = users.filter(is_superuser=True)

    for user in users:
        try:
            user.is_email_verified = user.profile.email_verified
        except UserProfile.DoesNotExist:
            user.is_email_verified = False

    context = {
        'users': users,
        'query': query,
        'status_filter': status_filter,
        'active_page': 'accounts',
        'stats_total': User.objects.count(),
        'stats_active': User.objects.filter(is_active=True).count(),
        'stats_verified': UserProfile.objects.filter(email_verified=True).count(),
        'stats_admin': User.objects.filter(is_superuser=True).count(),
    }
    return render(request, 'restaurants/admin_user_accounts.html', context)


@user_passes_test(lambda u: u.is_superuser)
def admin_user_account_action(request, user_id, action):
    target_user = get_object_or_404(User, pk=user_id)
    redirect_to = request.META.get('HTTP_REFERER') or reverse('admin_user_accounts')

    if action == 'activate':
        target_user.is_active = True
        target_user.save(update_fields=['is_active'])
        flash_msg.success(request, f"Da kich hoat tai khoan '{target_user.username}'.")
        return redirect(redirect_to)

    if action == 'deactivate':
        if target_user.id == request.user.id:
            flash_msg.error(request, 'Khong the tu khoa tai khoan dang dang nhap.')
            return redirect(redirect_to)
        target_user.is_active = False
        target_user.save(update_fields=['is_active'])
        flash_msg.success(request, f"Da khoa tai khoan '{target_user.username}'.")
        return redirect(redirect_to)

    if action in ['verify', 'unverify']:
        profile, _ = UserProfile.objects.get_or_create(user=target_user)
        is_verified = action == 'verify'
        profile.email_verified = is_verified
        if is_verified:
            profile.email_verification_token = ''
            profile.email_verification_expires = None
            if not target_user.is_active:
                target_user.is_active = True
                target_user.save(update_fields=['is_active'])
        profile.save(update_fields=['email_verified', 'email_verification_token', 'email_verification_expires'])

        if is_verified:
            flash_msg.success(request, f"Da xac minh email cho '{target_user.username}'.")
        else:
            flash_msg.warning(request, f"Da bo xac minh email cua '{target_user.username}'.")
        return redirect(redirect_to)

    flash_msg.error(request, 'Hanh dong khong hop le.')
    return redirect(redirect_to)


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
    ensure_default_amenity_categories()

    if pk:
        restaurant = get_object_or_404(Restaurant.objects.prefetch_related('gallery_images'), pk=pk)
        action_title = "CẬP NHẬT QUÁN ĂN"
    else:
        restaurant = None
        action_title = "THÊM QUÁN MỚI"

    def build_context(selected_amenity_ids=None, amenity_notes_override=None):
        amenity_categories = AmenityCategory.objects.all().order_by('order')

        if selected_amenity_ids is None:
            if restaurant:
                selected_amenity_ids = list(
                    restaurant.amenities.values_list('category_id', flat=True)
                )
            else:
                selected_amenity_ids = []

        normalized_ids = []
        for amenity_id in selected_amenity_ids:
            try:
                normalized_ids.append(int(amenity_id))
            except (TypeError, ValueError):
                continue

        if amenity_notes_override is None:
            amenity_notes = {}
            if restaurant:
                for amenity in restaurant.amenities.all():
                    amenity_notes[amenity.category_id] = amenity.note
        else:
            amenity_notes = amenity_notes_override

        return {
            'restaurant': restaurant,
            'districts': Restaurant.DISTRICT_CHOICES,
            'action_title': action_title,
            'active_page': 'restaurants',
            'amenity_categories': amenity_categories,
            'restaurant_amenity_ids': normalized_ids,
            'amenity_notes': amenity_notes,
        }

    if request.method == "POST":
        name = request.POST.get('name')
        address = request.POST.get('address')
        district = request.POST.get('district')
        description = request.POST.get('description', '')
        long_description = request.POST.get('long_description', '')
        image = request.FILES.get('image')
        gallery_images = request.FILES.getlist('gallery_images')
        is_pickup_available = request.POST.get('is_pickup_available') == 'on'
        amenity_ids = request.POST.getlist('amenities')

        amenity_notes_from_post = {}
        for amenity_id in amenity_ids:
            try:
                amenity_notes_from_post[int(amenity_id)] = request.POST.get(
                    f'amenity_notes_{amenity_id}',
                    ''
                ).strip()
            except (TypeError, ValueError):
                continue

        lat_raw = (request.POST.get('lat') or '').strip()
        lng_raw = (request.POST.get('lng') or '').strip()
        try:
            lat = float(lat_raw)
            lng = float(lng_raw)
        except (TypeError, ValueError):
            flash_msg.error(
                request,
                "Vui lòng chọn vị trí hợp lệ trên bản đồ (nhấp lên bản đồ hoặc bấm tìm địa chỉ trước khi lưu)."
            )
            return render(
                request,
                'restaurants/admin_form.html',
                build_context(
                    selected_amenity_ids=amenity_ids,
                    amenity_notes_override=amenity_notes_from_post
                )
            )

        pnt = Point(lng, lat, srid=4326)

        if restaurant:
            restaurant.name = name
            restaurant.address = address
            restaurant.district = district
            restaurant.description = description
            restaurant.long_description = long_description
            restaurant.location = pnt
            restaurant.is_pickup_available = is_pickup_available
            if image:
                restaurant.image = image
            restaurant.save()

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
                description=description,
                long_description=long_description,
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

        # ============================================
        # HANDLE AMENITIES
        # ============================================
        # Clear existing amenities
        restaurant.amenities.all().delete()

        # Add selected amenities
        for amenity_id in amenity_ids:
            notes = request.POST.get(f'amenity_notes_{amenity_id}', '').strip()
            RestaurantAmenity.objects.create(
                restaurant=restaurant,
                category_id=amenity_id,
                note=notes,
                is_available=True
            )

        return redirect('admin_restaurant_list')

    return render(request, 'restaurants/admin_form.html', build_context())


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
    expire_overdue_reservations(restaurant)

    bookings = Reservation.objects.filter(
        table__restaurant=restaurant
    ).order_by('-booking_time')
    return render(request, 'restaurants/admin_booking_list.html', {'restaurant': restaurant, 'bookings': bookings})


@user_passes_test(lambda u: u.is_superuser)
def admin_all_bookings(request):
    expire_overdue_reservations()

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
    duplicate_feedback_message = (
        "Email này đã gửi đánh giá trước đó.\n"
        "Mỗi Gmail chỉ được gửi 1 đánh giá trên hệ thống.\n"
        "Vui lòng dùng Gmail khác nếu muốn gửi thêm phản hồi."
    )

    if request.method == 'POST':
        customer_name = request.POST.get('customer_name', '').strip()
        customer_email = request.POST.get('customer_email', '').strip().lower()
        rating = request.POST.get('rating')
        message = request.POST.get('message', '').strip()

        # Mỗi Gmail chỉ được đánh giá 1 lần trên toàn hệ thống.
        if Feedback.objects.filter(customer_email__iexact=customer_email).exists():
            flash_msg.error(
                request,
                duplicate_feedback_message
            )
            return redirect('feedback_form', pk=pk)

        try:
            with transaction.atomic():
                feedback = Feedback.objects.create(
                    restaurant=restaurant,
                    customer_name=customer_name,
                    customer_email=customer_email,
                    rating=rating,
                    message=message
                )
        except IntegrityError:
            flash_msg.error(
                request,
                duplicate_feedback_message
            )
            return redirect('feedback_form', pk=pk)

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
    feedbacks = restaurant.feedbacks.all().order_by('-created_at')
    unread_count = feedbacks.filter(is_read=False).count()

    context = {
        'restaurant': restaurant,
        'feedbacks': feedbacks,
        'total_feedbacks': feedbacks.count(),
        'unread_count': unread_count,
        'active_page': 'all_feedbacks'
    }
    return render(request, 'restaurants/admin_feedback_list.html', context)


@user_passes_test(lambda u: u.is_superuser)
def admin_all_feedbacks(request):
    feedbacks = Feedback.objects.all().select_related('restaurant').order_by('-created_at')

    query = (request.GET.get('q') or '').strip()
    if query:
        feedbacks = feedbacks.filter(
            Q(customer_name__icontains=query) |
            Q(customer_email__icontains=query) |
            Q(message__icontains=query) |
            Q(restaurant__name__icontains=query)
        )

    restaurant_id = request.GET.get('restaurant_id')
    restaurant_name = None
    if restaurant_id:
        feedbacks = feedbacks.filter(restaurant_id=restaurant_id)
        restaurant_name = Restaurant.objects.get(id=restaurant_id).name

    rating = request.GET.get('rating')
    if rating:
        feedbacks = feedbacks.filter(rating=rating)

    read_status = (request.GET.get('read_status') or 'all').strip()
    if read_status == 'read':
        feedbacks = feedbacks.filter(is_read=True)
    elif read_status == 'unread':
        feedbacks = feedbacks.filter(is_read=False)

    all_restaurants = Restaurant.objects.all().order_by('name')

    context = {
        'feedbacks': feedbacks,
        'all_restaurants': all_restaurants,
        'query': query,
        'restaurant_id': restaurant_id,
        'restaurant_name': restaurant_name,
        'rating': rating,
        'read_status': read_status,
        'total_feedbacks': feedbacks.count(),
        'unread_feedbacks': feedbacks.filter(is_read=False).count(),
        'active_page': 'all_feedbacks'
    }
    return render(request, 'restaurants/admin_all_feedbacks.html', context)


@user_passes_test(lambda u: u.is_superuser)
def admin_mark_feedback_as_read(request, feedback_id):
    feedback = get_object_or_404(Feedback, pk=feedback_id)
    feedback.is_read = True
    feedback.save(update_fields=['is_read'])
    flash_msg.success(request, "Đã đánh dấu phản hồi này là đã xem.")
    redirect_to = request.META.get('HTTP_REFERER') or reverse('admin_feedback_list', kwargs={'pk': feedback.restaurant.pk})
    return redirect(redirect_to)


@user_passes_test(lambda u: u.is_superuser)
def admin_feedback_action(request, feedback_id, action):
    feedback = get_object_or_404(Feedback, pk=feedback_id)
    redirect_to = request.META.get('HTTP_REFERER') or reverse('admin_all_feedbacks')

    if action == 'read':
        feedback.is_read = True
        feedback.save(update_fields=['is_read'])
        flash_msg.success(request, "Đã đánh dấu phản hồi là đã xem.")
        return redirect(redirect_to)

    if action == 'unread':
        feedback.is_read = False
        feedback.save(update_fields=['is_read'])
        flash_msg.success(request, "Đã chuyển phản hồi về trạng thái chưa xem.")
        return redirect(redirect_to)

    if action == 'delete':
        feedback.delete()
        flash_msg.warning(request, "Đã xóa phản hồi.")
        return redirect(redirect_to)

    flash_msg.error(request, "Hành động không hợp lệ.")
    return redirect(redirect_to)


@user_passes_test(lambda u: u.is_superuser)
def admin_amenity_list(request):
    ensure_default_amenity_categories()

    if request.method == 'POST':
        amenity_id = request.POST.get('amenity_id')
        name = (request.POST.get('name') or '').strip()
        icon = (request.POST.get('icon') or '').strip()
        description = (request.POST.get('description') or '').strip()
        order_raw = (request.POST.get('order') or '0').strip()

        if not name:
            flash_msg.error(request, 'Tên tiện ích không được để trống.')
            return redirect('admin_amenity_list')
        if not icon:
            flash_msg.error(request, 'Icon không được để trống.')
            return redirect('admin_amenity_list')

        try:
            order = int(order_raw)
        except ValueError:
            order = 0

        if amenity_id:
            amenity = get_object_or_404(AmenityCategory, pk=amenity_id)
            amenity.name = name
            amenity.icon = icon
            amenity.description = description
            amenity.order = order
            try:
                amenity.save()
                flash_msg.success(request, f"Đã cập nhật tiện ích '{name}'.")
            except IntegrityError:
                flash_msg.error(request, 'Tên tiện ích đã tồn tại. Vui lòng chọn tên khác.')
            return redirect('admin_amenity_list')

        try:
            AmenityCategory.objects.create(
                name=name,
                icon=icon,
                description=description,
                order=order
            )
            flash_msg.success(request, f"Đã thêm tiện ích '{name}'.")
        except IntegrityError:
            flash_msg.error(request, 'Tên tiện ích đã tồn tại. Vui lòng chọn tên khác.')
        return redirect('admin_amenity_list')

    edit_id = request.GET.get('edit')
    edit_item = None
    if edit_id:
        edit_item = get_object_or_404(AmenityCategory, pk=edit_id)

    amenities = AmenityCategory.objects.annotate(
        used_count=Count('restaurant_amenities')
    ).order_by('order', 'name')

    context = {
        'amenities': amenities,
        'edit_item': edit_item,
        'icon_presets': AMENITY_ICON_PRESETS,
        'active_page': 'amenities',
    }
    return render(request, 'restaurants/admin_amenity_list.html', context)


@user_passes_test(lambda u: u.is_superuser)
def admin_amenity_delete(request, amenity_id):
    amenity = get_object_or_404(AmenityCategory, pk=amenity_id)
    if amenity.restaurant_amenities.exists():
        flash_msg.error(
            request,
            f"Không thể xóa '{amenity.name}' vì đã được gán cho quán ăn."
        )
        return redirect('admin_amenity_list')

    amenity_name = amenity.name
    amenity.delete()
    flash_msg.warning(request, f"Đã xóa tiện ích '{amenity_name}'.")
    return redirect('admin_amenity_list')


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
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[getattr(settings, 'FEEDBACK_NOTIFY_EMAIL', 'admin@giseatery.com')],
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
        from_email=settings.DEFAULT_FROM_EMAIL,
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
        
        # Trả về tất cả kết quả (không chỉ kết quả đầu tiên)
        results = response.json()
        if results:
            # Transform kết quả để match với frontend expectations
            formatted_results = []
            for result in results:
                try:
                    lat_value = float(result.get('lat'))
                    lon_value = float(result.get('lon'))
                except (TypeError, ValueError):
                    continue

                formatted_results.append({
                    'lat': lat_value,
                    'lon': lon_value,
                    'lng': lon_value,  # Alias để frontend dùng lat/lng thống nhất
                    'address': result.get('display_name', ''),
                    'display_name': result.get('display_name', '')
                })

            return JsonResponse(formatted_results, safe=False)
        else:
            return JsonResponse([], safe=False)

    except requests.RequestException as e:
        print(f'[Geocoding Error] {str(e)}')
        # Return empty array khi có lỗi để frontend handle gracefully
        return JsonResponse({
            'error': 'Không thể kết nối dịch vụ geocoding. Vui lòng thử lại hoặc nhập tọa độ thủ công.',
            'status': 'error'
        }, status=500)


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
        print(f'[Reverse Geocoding Error] {str(e)}')
        # Return empty object khi có lỗi để frontend handle gracefully
        return JsonResponse({
            'error': 'Không thể kết nối dịch vụ geocoding. Vui lòng thử lại.',
            'status': 'error'
        }, status=500)



