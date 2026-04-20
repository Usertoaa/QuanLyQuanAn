from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views

urlpatterns = [
    # Trang chính
    path('', views.index, name='index'),
    path('map/', views.user_map, name='user_map'),
    path('map/<int:pk>/', views.map_detail, name='map_detail'),
    path('my-history/', views.user_booking_history, name='user_booking_history'),

    # API URLs

    path('api/restaurants/', views.api_get_restaurants, name='api_get_restaurants'),
    path('api/nearby/', views.api_nearby_restaurants, name='api_nearby'),
    path('api/book/', views.api_book_table, name='api_book_table'),
    path('api/pickup/', views.api_pickup_order, name='api_pickup_order'),
    path('api/geocode-address/', views.api_geocode_address, name='api_geocode_address'),
    path('api/reverse-geocode-address/', views.api_reverse_geocode_address, name='api_reverse_geocode_address'),
    
    # Admin URLs
    path('admin/', views.admin_dashboard, name='admin_dashboard'),

    # Quản lý quán ăn
    path('my-admin/restaurants/', views.admin_restaurant_list, name='admin_restaurant_list'),
    path('my-admin/restaurants/add/', views.admin_restaurant_form, name='admin_restaurant_add'),
    path('my-admin/restaurants/edit/<int:pk>/', views.admin_restaurant_form, name='admin_restaurant_edit'),
    path('my-admin/restaurants/delete/<int:pk>/', views.admin_restaurant_delete, name='admin_restaurant_delete'),

    # Quản lý đặt bàn
    path('my-admin/all-bookings/', views.admin_all_bookings, name='admin_reservations'),
    path('my-admin/restaurant/<int:pk>/bookings/', views.admin_booking_list, name='admin_booking_list'),
    path('restaurant/<int:pk>/', views.restaurant_detail, name='restaurant_detail'),
    path('my-admin/booking/update/<int:booking_id>/<str:status>/', views.admin_update_booking_status, name='admin_update_booking_status'),

    # Quản lý món ăn
    path('my-admin/restaurant/<int:pk>/menu/', views.admin_menu_list, name='admin_menu_list'),
    path('my-admin/restaurant/<int:pk>/menu/import/', views.admin_import_dishes, name='admin_import_dishes'),
    path('my-admin/restaurant/<int:pk>/menu/import/download-template/', views.download_sample_dishes_template, name='download_sample_dishes_template'),
    path('my-admin/restaurant/<int:pk>/menu/add/', views.admin_dish_form, name='admin_dish_add'),
    path('my-admin/menu/edit/<int:dish_id>/', views.admin_dish_edit, name='admin_dish_edit'),
    path('my-admin/menu/delete/<int:dish_id>/', views.admin_dish_delete, name='admin_dish_delete'),

    # Quản lý phản hồi
    path('restaurant/<int:pk>/feedback/', views.feedback_form, name='feedback_form'),
    path('my-admin/restaurant/<int:pk>/feedbacks/', views.admin_feedback_list, name='admin_feedback_list'),
    path('my-admin/all-feedbacks/', views.admin_all_feedbacks, name='admin_all_feedbacks'),
    path('my-admin/feedback/<int:feedback_id>/read/', views.admin_mark_feedback_as_read, name='mark_feedback_as_read'),

    # Đăng ký / đăng nhập / đăng xuất
    path('register/', views.register_view, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='restaurants/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='index'), name='logout'),
    
    # Email verification & Password reset
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),
    path('verification-pending/', views.verification_pending, name='verification_pending'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/<str:token>/', views.reset_password, name='reset_password'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)