"""
Script để thêm mô tả cho các quán ăn
Chạy với: python manage.py shell < add_descriptions.py
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GIS_Eatery.settings')
django.setup()

from restaurants.models import Restaurant

# Dữ liệu mô tả cho các quán ăn nổi tiếng TP.HCM
descriptions = {
    # Mô tả ngắn và mô tả dài
    "Phở Hòa": {
        "short": "Phở truyền thống Hà Nội, nước dùi đậm đà",
        "long": """Phở Hòa là một trong những quán phở nổi tiếng nhất TP.HCM với hơn 30 năm kinh nghiệm.
Quán chuyên phục vụ phở truyền thống Hà Nội với nước dùi được nấu từ xương bò và gà trong 12 giờ liên tục.
Các loại thịt được lựa chọn từ những con bò tươi nhất mỗi sáng.
Phở Hòa là địa điểm lý tưởng cho những ai yêu thích phở ngon, xứng đáng bỏ ra một chút thời gian chờ đợi.

Giờ hoạt động: 6:00 - 21:00 (Mở cửa hàng ngày)
Điểm nhấn: Phở bò, Phở gà, Bánh mì nướng
Dịch vụ: Nhận đặt bàn, Tận nơi, Ăn tại quán"""
    },
    "Cơm Tấm Cô Ba": {
        "short": "Cơm tấm tây côi, thịt nướng ngon lạ",
        "long": """Cơm Tấm Cô Ba là địa chỉ quân quân với cơm tấm truyền thống TP.HCM.
Cơm tấm được làm từ cơm tấy côi thơm, kết hợp với thịt nướng mềm, trứng chiên hoặc nướng.
Quán cũng phục vụ các món ăn kèm như nước mắm chua, dưa leo, canh chua cá.
Không gian quán giản dị, sạch sẽ, giá cả phải chăng - phù hợp cho ăn sáng hoặc bữa trưa.

Giờ hoạt động: 5:30 - 14:00 (Đóng cửa chiều)
Điểm nhấn: Cơm tấm tây côi, Cơm tấm với nạm nướng
Dịch vụ: Ăn tại quán, Bán mang về"""
    },
    "Bánh Mì Ông Ngoại": {
        "short": "Bánh mì Sài Gòn cổ truyền, báo chế ngon",
        "long": """Bánh Mì Ông Ngoại là điểm dừng chân yêu thích của bao thế hệ Sài Gòn.
Bánh được làm tươi mỗi sáng từ lò nướng truyền thống, giòn tan, khô ráp.
Nhân bánh được chế biến công phu với pâtê tự làm, chả lụa, giò thủ, dưa chua, rau sống tươi.
Quán phục vụ nhanh, giá rẻ - lý tưởng cho bữa sáng vội hoặc bữa xế chiều.

Giờ hoạt động: 5:30 - 18:00
Điểm nhấn: Bánh mì pâtê, Bánh mì chả cốt, Bánh mì thịt nạm
Dịch vụ: Bán mang về, Ăn tại quán"""
    },
    "Bún Chả Hà Nội": {
        "short": "Bún chả Hà Nội thơm nức, thịt nướng tuyệt",
        "long": """Bún Chả Hà Nội mang đến hương vị chuẩn xứ Kinh với công thức truyền thống.
Nước mắm chua ngọt được pha chế với cân đối hoàn hảo.
Thịt nướng chín giòn vàng, thơm lửa, kết hợp với bún tươi, rau sống tươi mát.
Quán có không gian yên tĩnh, thích hợp cho gia đình hoặc nhóm bạn.

Giờ hoạt động: 10:00 - 22:00
Điểm nhấn: Bún chả thập cẩm, Nem nướng, Bánh cuốn
Dịch vụ: Ăn tại quán, Đặt tiệc, Giao hàng"""
    },
    "Canh Chua Cá": {
        "short": "Canh chua cá ba sa, chua cay vừa vặn",
        "long": """Canh Chua Cá là nhà hàng chuyên phục vụ các món canh truyền thống miền Nam.
Cá ba sa tươi sống được nấu cùng với chua cây, mộc nhật, hành lá, ớt tươi.
Canh được nấu theo công thức truyền thống, vừa chua vừa cay, kích thích vị giác.
Kèm theo là cơm tấm trắng nóng, dưa leo, canh được nấu mới mỗi hôm.

Giờ hoạt động: 10:30 - 21:30
Điểm nhấn: Canh chua cá ba sa, Canh chua tôm, Cánh gà nước mắm
Dịch vụ: Ăn tại quán, Giao hàng, Đặt tiệc"""
    },
    "Lẩu Vua": {
        "short": "Lẩu nóng hổi, nước lẩu đậm đà, tươi ngon",
        "long": """Lẩu Vua là địa chỉ quán lẩu chất lượng cao tại TP.HCM.
Nước lẩu được nấu từ xương bò, xương gà, cua cà chua trong nhiều giờ.
Các loại thịt, hải sản, rau được chọn lọc kỹ, tươi sống, vệ sinh cao.
Quán có không gian thoải mái, điều hòa mát, thích hợp để ăn tối với gia đình hoặc bạn bè.

Giờ hoạt động: 16:00 - 23:00
Điểm nhấn: Lẩu Thái cay, Lẩu nước dùi, Lẩu hải sản
Dịch vụ: Ăn tại quán, Đặt tiệc, Free wifi"""
    },
    "Mỳ Quảng Nước": {
        "short": "Mỳ Quảng chuẩn vị Trung Bộ, nước dùi đậm",
        "long": """Mỳ Quảng Nước mang đến hương vị chuẩn xứ miền Trung Việt Nam.
Mỳ Quảng được nấu theo công thức truyền thống với nước dùi từ xương và cua.
Kèm theo là thịt gà, tôm sú, bánh hỏi vàng ươm, rau sống đủ loại.
Quán có phục vụ tận tình, giá cả hợp lý, lý tưởng cho bữa trưa hoặc bữa tối gia đình.

Giờ hoạt động: 10:00 - 21:00
Điểm nhấn: Mỳ Quảng nước, Mỳ Quảng khô, Bánh hỏi
Dịch vụ: Ăn tại quán, Bán mang về"""
    },
    "Tô Cua Cà Chua": {
        "short": "Cua cà chua nước mắm, đặc sản Sài Gòn",
        "long": """Tô Cua Cà Chua là quán chuyên phục vụ món cua cà chua nổi tiếng TP.HCM.
Cua tươi sống từ Đồng Tháp được xử lý sạch sẽ, nấu cùng với cà chua chín và nước mắm chua.
Nước canh có vị cay nồng, cua thịt chắc, cà chua mềm - kết hợp hoàn hảo.
Quán có không gian vệ sinh, thoáng mát, phục vụ nhanh chóng.

Giờ hoạt động: 11:00 - 22:00
Điểm nhấn: Cua cà chua, Tôm cà chua, Canh chua cua
Dịch vụ: Ăn tại quán, Giao hàng, Đặt tiệc"""
    }
}

# Lấy tất cả quán ăn
restaurants = Restaurant.objects.all()

print(f"Tìm thấy {restaurants.count()} quán ăn")
print("=" * 60)

updated = 0
for restaurant in restaurants:
    # Tìm mô tả dựa trên tên quán
    for name, desc in descriptions.items():
        if name.lower() in restaurant.name.lower():
            restaurant.description = desc["short"]
            restaurant.long_description = desc["long"]
            restaurant.save()
            print(f"✅ Cập nhật: {restaurant.name}")
            updated += 1
            break
    else:
        # Nếu không tìm thấy mô tả cụ thể, thêm mô tả generic
        if not restaurant.description:
            restaurant.description = f"Nhà hàng {restaurant.name} nổi tiếng tại {restaurant.get_district_display()}"
            restaurant.long_description = f"""Nhà hàng {restaurant.name} là một địa chỉ ưa thích tại {restaurant.get_district_display()}, TP.HCM.

Quán cung cấp các món ăn ngon, chất lượng cao với dịch vụ tận tình.
Không gian quán thoáng mát, sạch sẽ, phù hợp cho ăn gia đình hoặc tập thể.
Quán chào đón khách hàng hàng ngày từ sáng đến tối.

Vui lòng liên hệ quán để biết thêm chi tiết về menu và các dịch vụ khác."""
            restaurant.save()
            print(f"✅ Thêm mô tả mặc định: {restaurant.name}")
            updated += 1

print("=" * 60)
print(f"Tổng cộng: {updated}/{restaurants.count()} quán ăn đã được cập nhật")
