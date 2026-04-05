from django.contrib.gis.db import models 
from django.contrib.auth.models import User

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
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    district = models.CharField(max_length=5, choices=DISTRICT_CHOICES, verbose_name="Quận/Huyện")
    image = models.ImageField(upload_to='restaurant_images/', blank=True, null=True, verbose_name="Ảnh quán")
    location = models.PointField(srid=4326)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Table(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='tables')
    table_number = models.CharField(max_length=10)
    capacity = models.IntegerField(default=4)
    is_available = models.BooleanField(default=True)

class Reservation(models.Model):
    table = models.ForeignKey(Table, on_delete=models.CASCADE)
    customer_name = models.CharField(max_length=100)
    booking_time = models.DateTimeField()
    number_of_people = models.IntegerField()
    STATUS_CHOICES = [
        ('pending', '⏳ Chờ xác nhận'),
        ('confirmed', '✅ Đã duyệt'),
        ('cancelled', '❌ Đã hủy'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Trạng thái")

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Tài khoản đặt")

    def __str__(self):
        return f"{self.customer_name} - {self.booking_time}"
    
class Dish(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='dishes')
    name = models.CharField(max_length=200, verbose_name="Tên món")
    description = models.TextField(blank=True, verbose_name="Mô tả")
    price = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="Giá tiền")
    image = models.ImageField(upload_to='dishes/', blank=True, null=True, verbose_name="Ảnh món")
    is_available = models.BooleanField(default=True, verbose_name="Còn món")

    def __str__(self):
        return f"{self.name} ({self.restaurant.name})"

class Feedback(models.Model):
    """Model lưu phản hồi từ khách hàng"""
    RATING_CHOICES = [
        (1, '⭐ Rất tệ'),
        (2, '⭐⭐ Tệ'),
        (3, '⭐⭐⭐ Bình thường'),
        (4, '⭐⭐⭐⭐ Tốt'),
        (5, '⭐⭐⭐⭐⭐ Tuyệt vời'),
    ]
    
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='feedbacks')
    customer_name = models.CharField(max_length=100, verbose_name="Tên khách hàng")
    customer_email = models.EmailField(verbose_name="Email")
    rating = models.IntegerField(choices=RATING_CHOICES, verbose_name="Đánh giá")
    message = models.TextField(verbose_name="Nội dung phản hồi")
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False, verbose_name="Đã xem")
    
    def __str__(self):
        return f"{self.customer_name} - {self.restaurant.name} ({self.get_rating_display()})"

    class Meta:
        ordering = ['-created_at']

class RestaurantImage(models.Model):
    """Model để lưu ảnh gallery của quán"""
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='gallery',
        verbose_name="Quán ăn"
    )
    image = models.ImageField(upload_to='restaurant_gallery/', verbose_name="Ảnh")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ảnh của {self.restaurant.name}"

    class Meta:
        verbose_name = "Ảnh quán ăn"
        verbose_name_plural = "Ảnh quán ăn"




