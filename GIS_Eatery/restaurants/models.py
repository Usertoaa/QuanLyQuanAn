from django.contrib.gis.db import models
from django.conf import settings


class Restaurant(models.Model):
    DISTRICT_CHOICES = [
        ('1', 'Quận 1'),
        ('3', 'Quận 3'),
        ('4', 'Quận 4'),
        ('5', 'Quận 5'),
        ('6', 'Quận 6'),
        ('7', 'Quận 7'),
        ('8', 'Quận 8'),
        ('10', 'Quận 10'),
        ('11', 'Quận 11'),
        ('12', 'Quận 12'),
        ('TB', 'Tân Bình'),
        ('TP', 'Tân Phú'),
        ('BT', 'Bình Thạnh'),
        ('PN', 'Phú Nhuận'),
        ('GV', 'Gò Vấp'),
        ('TD', 'Thủ Đức'),
    ]

    name = models.CharField(max_length=200, verbose_name="Tên quán")
    address = models.CharField(max_length=300, verbose_name="Địa chỉ")
    district = models.CharField(
        max_length=10,
        choices=DISTRICT_CHOICES,
        verbose_name="Quận/Huyện"
    )
    description = models.TextField(blank=True, null=True, verbose_name="Mô tả")
    image = models.ImageField(
        upload_to='restaurant_images/',
        blank=True,
        null=True,
        verbose_name="Ảnh quán"
    )
    location = models.PointField(srid=4326, verbose_name="Vị trí")
    created_at = models.DateTimeField(auto_now_add=True)
    is_pickup_available = models.BooleanField(
        default=False,
        verbose_name="Cho phép đặt trước đến lấy món"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Quán ăn"
        verbose_name_plural = "Quán ăn"

    def __str__(self):
        return self.name


class RestaurantImage(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='gallery_images',
        verbose_name="Quán ăn"
    )
    image = models.ImageField(
        upload_to='restaurant_gallery/',
        verbose_name="Ảnh"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = "Ảnh quán ăn"
        verbose_name_plural = "Ảnh quán ăn"

    def __str__(self):
        return f"Ảnh của {self.restaurant.name}"


class Table(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='tables'
    )
    table_number = models.CharField(max_length=10, verbose_name="Số bàn")
    capacity = models.PositiveIntegerField(default=4, verbose_name="Sức chứa")
    is_available = models.BooleanField(default=True, verbose_name="Còn sử dụng")

    class Meta:
        ordering = ['id']
        verbose_name = "Bàn"
        verbose_name_plural = "Bàn"

    def __str__(self):
        return f"{self.table_number} - {self.restaurant.name}"


class Reservation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Chờ duyệt'),
        ('confirmed', 'Đã xác nhận'),
        ('waiting', 'Hàng chờ'),
        ('completed', 'Hoàn thành'),
        ('cancelled', 'Đã hủy'),
    ]

    table = models.ForeignKey(
        Table,
        on_delete=models.CASCADE,
        related_name='reservations'
    )
    customer_name = models.CharField(max_length=100, verbose_name="Tên khách hàng")
    customer_phone = models.CharField(max_length=20, blank=True, verbose_name="Số điện thoại")
    booking_time = models.DateTimeField(verbose_name="Thời gian đặt")
    number_of_people = models.PositiveIntegerField(verbose_name="Số người")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Trạng thái"
    )
    queue_position = models.PositiveIntegerField(
        default=0,
        verbose_name="Số thứ tự hàng chờ"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reservations'
    )
    note = models.TextField(blank=True, verbose_name="Ghi chú")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-booking_time']
        verbose_name = "Đặt bàn"
        verbose_name_plural = "Đặt bàn"

    def __str__(self):
        return f"{self.customer_name} - {self.table.restaurant.name} - {self.booking_time}"
    
    def get_total_price(self):
        """Tính tổng giá tiền của các món đã chọn"""
        return sum(item.dish.price * item.quantity for item in self.items.all())
    
    def get_items_count(self):
        """Lấy tổng số lượng món"""
        return sum(item.quantity for item in self.items.all())


class ReservationItem(models.Model):
    """Lưu các món ăn được chọn trong một đơn đặt bàn"""
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Đơn đặt bàn"
    )
    dish = models.ForeignKey(
        'Dish',
        on_delete=models.CASCADE,
        related_name='reservation_items',
        verbose_name="Món ăn"
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="Số lượng")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Chi tiết đơn đặt bàn"
        verbose_name_plural = "Chi tiết đơn đặt bàn"
        unique_together = ['reservation', 'dish']

    def __str__(self):
        return f"{self.dish.name} x {self.quantity} - {self.reservation}"
    
    def get_subtotal(self):
        """Tính tổng giá của món này"""
        return self.dish.price * self.quantity


class Dish(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='dishes'
    )
    name = models.CharField(max_length=200, verbose_name="Tên món")
    description = models.TextField(blank=True, verbose_name="Mô tả")
    price = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="Giá tiền")
    image = models.ImageField(
        upload_to='dishes/',
        blank=True,
        null=True,
        verbose_name="Ảnh món"
    )
    is_available = models.BooleanField(default=True, verbose_name="Còn món")
    is_price_representative = models.BooleanField(
        default=False,
        verbose_name="Dùng làm giá đại diện"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Món ăn"
        verbose_name_plural = "Món ăn"

    def __str__(self):
        return f"{self.name} ({self.restaurant.name})"


class Feedback(models.Model):
    RATING_CHOICES = [
        (1, '⭐ Rất tệ'),
        (2, '⭐⭐ Tệ'),
        (3, '⭐⭐⭐ Bình thường'),
        (4, '⭐⭐⭐⭐ Tốt'),
        (5, '⭐⭐⭐⭐⭐ Tuyệt vời'),
    ]

    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='feedbacks'
    )
    customer_name = models.CharField(max_length=100, verbose_name="Tên khách hàng")
    customer_email = models.EmailField(verbose_name="Email")
    rating = models.IntegerField(choices=RATING_CHOICES, verbose_name="Đánh giá")
    message = models.TextField(verbose_name="Nội dung phản hồi")
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False, verbose_name="Đã xem")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Phản hồi"
        verbose_name_plural = "Phản hồi"
        constraints = [
            models.UniqueConstraint(
                fields=['restaurant', 'customer_email'],
                name='unique_feedback_email_per_restaurant'
            )
        ]

    def __str__(self):
        return f"{self.customer_name} - {self.restaurant.name} ({self.get_rating_display()})"


class PickupOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Chờ duyệt'),
        ('confirmed', 'Đã xác nhận'),
        ('ready', 'Sẵn sàng lấy'),
        ('completed', 'Đã nhận'),
        ('cancelled', 'Đã hủy'),
    ]

    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='pickup_orders',
        verbose_name="Quán"
    )
    customer_name = models.CharField(max_length=100, verbose_name="Tên khách hàng")
    customer_phone = models.CharField(max_length=20, verbose_name="Số điện thoại")
    pickup_time = models.DateTimeField(verbose_name="Thời gian đến lấy")
    note = models.TextField(blank=True, verbose_name="Ghi chú")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Trạng thái"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pickup_orders'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Đơn đặt lấy món"
        verbose_name_plural = "Đơn đặt lấy món"

    def __str__(self):
        return f"Đơn lấy món - {self.customer_name} - {self.restaurant.name}"


class PickupOrderItem(models.Model):
    pickup_order = models.ForeignKey(
        PickupOrder,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Đơn lấy món"
    )
    dish = models.ForeignKey(
        Dish,
        on_delete=models.CASCADE,
        related_name='pickup_order_items',
        verbose_name="Món ăn"
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="Số lượng")

    class Meta:
        verbose_name = "Chi tiết đơn lấy món"
        verbose_name_plural = "Chi tiết đơn lấy món"

    def __str__(self):
        return f"{self.dish.name} x {self.quantity}"


class UserProfile(models.Model):
    """
    Mở rộng Django User model để thêm email verification
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    email_verified = models.BooleanField(default=False, verbose_name="Email đã xác thực")
    email_verification_token = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Token xác thực email"
    )
    email_verification_expires = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Thời hạn xác thực email"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Thông tin người dùng"
        verbose_name_plural = "Thông tin người dùng"

    def __str__(self):
        return f"Profile - {self.user.username}"


class PasswordResetToken(models.Model):
    """
    Model để lưu token reset mật khẩu
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='password_reset_tokens'
    )
    token = models.CharField(max_length=100, unique=True, verbose_name="Token")
    expires_at = models.DateTimeField(verbose_name="Hết hạn lúc")
    is_used = models.BooleanField(default=False, verbose_name="Đã sử dụng")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Token reset mật khẩu"
        verbose_name_plural = "Token reset mật khẩu"
        ordering = ['-created_at']

    def __str__(self):
        return f"Reset token - {self.user.username}"