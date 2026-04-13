import requests
from datetime import datetime, timedelta

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
from django.contrib.auth import login
from django.contrib import messages as flash_msg
from django.core.mail import send_mail
from django.utils.html import strip_tags

from .models import (
    Restaurant,
    Table,
    Reservation,
    Dish,
    Feedback,
    RestaurantImage,
    PickupOrder,
    PickupOrderItem,
)

BOOKING_SLOT_MINUTES = 30
ACTIVE_RESERVATION_STATUSES = ['pending', 'confirmed', 'waiting']


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


# PHẦN 1: PUBLIC USER VIEWS

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
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            flash_msg.success(request, f"Chào mừng {user.username}!")
            return redirect('index')
        flash_msg.error(request, "Lỗi đăng ký. Vui lòng kiểm tra lại thông tin.")
    else:
        form = UserCreationForm()

    return render(request, 'restaurants/register.html', {'form': form})


@login_required(login_url='login')
def user_booking_history(request):
    my_bookings = Reservation.objects.filter(
        user=request.user
    ).select_related('table__restaurant').order_by('-booking_time')
    return render(request, 'restaurants/user_history.html', {'bookings': my_bookings})


# PHẦN 3: API ENDPOINTS

def api_get_restaurants(request):
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
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Yêu cầu không hợp lệ'})

    try:
        restaurant_id = request.POST.get('restaurant_id')
        customer_name = request.POST.get('name')
        booking_time_str = request.POST.get('time') or request.POST.get('booking_time')
        people = int(request.POST.get('people', 4))

        restaurant = Restaurant.objects.get(id=restaurant_id)

        if not restaurant.tables.exists():
            create_default_tables_for_restaurant(restaurant)

        requested_time = parse_user_datetime(booking_time_str)
        if requested_time is None:
            return JsonResponse({'status': 'error', 'message': 'Thời gian đặt bàn không hợp lệ.'})

        best_table, available_from = find_best_table_for_booking(
            restaurant=restaurant,
            people=people,
            requested_time=requested_time
        )

        if best_table is None:
            return JsonResponse({
                'status': 'error',
                'message': 'Không có bàn phù hợp với số lượng khách này.'
            })

        is_waiting = available_from > requested_time
        queue_position = 0

        if is_waiting:
            queue_position = Reservation.objects.filter(
                table=best_table,
                booking_time=available_from,
                status='waiting'
            ).count() + 1

        reservation = Reservation(
            table=best_table,
            customer_name=customer_name,
            booking_time=available_from,
            number_of_people=people,
            status='waiting' if is_waiting else 'pending',
            queue_position=queue_position
        )

        if request.user.is_authenticated:
            reservation.user = request.user

        reservation.save()

        if is_waiting:
            return JsonResponse({
                'status': 'success',
                'booking_type': 'waiting',
                'message': (
                    f'Hiện đã hết bàn đúng giờ bạn chọn. '
                    f'Bạn được đưa vào hàng chờ tại {best_table.table_number} '
                    f'lúc {available_from.strftime("%d/%m/%Y %H:%M")}. '
                    f'Số thứ tự chờ: {queue_position}.'
                )
            })

        return JsonResponse({
            'status': 'success',
            'booking_type': 'normal',
            'message': f'Thành công! Đơn đặt tại {restaurant.name} đang chờ duyệt.'
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': 'Lỗi server: ' + str(e)})


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
        return JsonResponse(response.json(), safe=False)

    except requests.RequestException as e:
        return JsonResponse({'error': f'Lỗi geocoding: {str(e)}'}, status=500)