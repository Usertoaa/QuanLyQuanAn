import os
import django
import random

# 1. Thiết lập môi trường
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GIS_Eatery.settings')
django.setup()

from django.contrib.gis.geos import Point
from restaurants.models import Restaurant, Table

def create_full_data():
    print("--- BẮT ĐẦU KHÔI PHỤC DỮ LIỆU ---")

    # 1. Tự động tạo Quán ăn (Nếu chưa có)
    if Restaurant.objects.count() == 0:
        print(">> Đang tạo quán ăn mẫu...")
        
        # Danh sách quán mẫu tại TP.HCM
        dummy_restaurants = [
            {"name": "Phở Hòa Pasteur", "address": "260C Pasteur, Q.3", "lng": 106.6908, "lat": 10.7828},
            {"name": "Cơm Tấm Cali", "address": "Quận 1, TP.HCM", "lng": 106.6990, "lat": 10.7750},
            {"name": "Pizza 4P's", "address": "Chợ Bến Thành", "lng": 106.6975, "lat": 10.7720},
        ]

        for data in dummy_restaurants:
            r = Restaurant.objects.create(
                name=data["name"],
                address=data["address"],
                location=Point(data["lng"], data["lat"], srid=4326) # Tạo tọa độ GIS
            )
            print(f"   + Đã tạo: {r.name}")
    else:
        print(">> Quán ăn đã có sẵn, không cần tạo thêm.")

    # 2. Tạo Bàn ăn cho từng quán
    print(">> Đang kiểm tra và tạo bàn ăn...")
    restaurants = Restaurant.objects.all()
    count_tables = 0

    for r in restaurants:
        if r.tables.count() == 0:
            # Tạo ngẫu nhiên 5-10 bàn cho mỗi quán
            num_tables = random.randint(5, 10)
            for i in range(1, num_tables + 1):
                Table.objects.create(
                    restaurant=r,
                    table_number=f"Bàn {i}",
                    capacity=4,
                    is_available=True
                )
            print(f"   + Quán '{r.name}': Đã thêm {num_tables} bàn.")
            count_tables += num_tables
        else:
            print(f"   - Quán '{r.name}' đã có bàn, bỏ qua.")

    print(f"--- HOÀN TẤT! Đã có dữ liệu đầy đủ để test. ---")

if __name__ == "__main__":
    create_full_data()