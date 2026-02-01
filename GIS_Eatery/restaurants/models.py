from django.contrib.gis.db import models 

class Restaurant(models.Model):
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    location = models.PointField(srid=4326) # Lưu tọa độ chuẩn GPS
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
