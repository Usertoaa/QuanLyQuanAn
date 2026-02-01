from django.db import models
from django.contrib.gis.db import models 

class Restaurant(models.Model):
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    # Lưu tọa độ (Kinh độ, Vĩ độ) theo chuẩn WGS84 (srid=4326)
    location = models.PointField(srid=4326) 
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
