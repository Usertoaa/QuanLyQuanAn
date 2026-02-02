from django.contrib.gis.db import models 

class Restaurant(models.Model):
    DISTRICT_CHOICES = [
        ('Q1', 'Quận 1'),
        ('Q3', 'Quận 3'),
        ('Q4', 'Quận 4'),
        ('Q5', 'Quận 5'),
        ('Q7', 'Quận 7'),
        ('BT', 'Bình Thạnh'),
        ('PN', 'Phú Nhuận'),
        ('TP', 'Tân Phú'),
    ]
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    district = models.CharField(max_length=10, choices=DISTRICT_CHOICES, default='Q1', verbose_name="Quận")
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
