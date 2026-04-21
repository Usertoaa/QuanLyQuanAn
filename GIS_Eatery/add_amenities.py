"""
Script để thêm các danh mục tiện ích mặc định
Chạy với: python manage.py shell < add_amenities.py
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GIS_Eatery.settings')
django.setup()

from restaurants.models import AmenityCategory

# Danh sách các tiện ích mặc định
amenities = [
    {
        'name': 'Free Wifi',
        'icon': 'fas fa-wifi',
        'order': 1,
        'description': 'Quán cung cấp dịch vụ wifi miễn phí cho khách hàng'
    },
    {
        'name': 'Máy lạnh',
        'icon': 'fas fa-snowflake',
        'order': 2,
        'description': 'Quán có hệ thống điều hòa không khí để làm mát'
    },
    {
        'name': 'Giữ xe',
        'icon': 'fas fa-parking',
        'order': 3,
        'description': 'Quán cung cấp dịch vụ giữ xe miễn phí cho khách'
    },
    {
        'name': 'Bàn hút khói',
        'icon': 'fas fa-fan',
        'order': 4,
        'description': 'Quán có bàn hút khói cho khách hút thuốc'
    },
    {
        'name': 'Toilet sạch',
        'icon': 'fas fa-restroom',
        'order': 5,
        'description': 'Quán có nhà vệ sinh sạch sẽ và hiện đại'
    },
    {
        'name': 'Đặt bàn trước',
        'icon': 'fas fa-calendar-alt',
        'order': 6,
        'description': 'Quán cho phép khách đặt bàn trước'
    },
    {
        'name': 'Giao hàng',
        'icon': 'fas fa-motorcycle',
        'order': 7,
        'description': 'Quán cung cấp dịch vụ giao hàng đến tận nơi'
    },
    {
        'name': 'Có bàn cao',
        'icon': 'fas fa-chair',
        'order': 8,
        'description': 'Quán có bàn cao phù hợp cho làm việc hoặc chờ'
    },
    {
        'name': 'Nhạc sống',
        'icon': 'fas fa-music',
        'order': 9,
        'description': 'Quán có buổi biểu diễn âm nhạc sống'
    },
    {
        'name': 'Phòng VIP',
        'icon': 'fas fa-crown',
        'order': 10,
        'description': 'Quán có phòng riêng biệt cho nhóm lớn hoặc VIP'
    },
]

print("Thêm danh mục tiện ích...")
print("=" * 60)

created = 0
for amenity in amenities:
    obj, is_created = AmenityCategory.objects.get_or_create(
        name=amenity['name'],
        defaults={
            'icon': amenity['icon'],
            'order': amenity['order'],
            'description': amenity['description']
        }
    )
    if is_created:
        print(f"✅ Tạo: {amenity['name']}")
        created += 1
    else:
        print(f"ℹ️  Đã tồn tại: {amenity['name']}")

print("=" * 60)
print(f"Tổng cộng: {created} danh mục tiện ích mới được tạo")
