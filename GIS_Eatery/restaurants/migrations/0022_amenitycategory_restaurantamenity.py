# Generated manually for Amenity models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0021_restaurant_long_description'),
    ]

    operations = [
        migrations.CreateModel(
            name='AmenityCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Tên danh mục')),
                ('icon', models.CharField(help_text='Font Awesome icon class (vd: fas fa-wifi)', max_length=50, verbose_name='Icon')),
                ('description', models.TextField(blank=True, verbose_name='Mô tả')),
                ('order', models.IntegerField(default=0, verbose_name='Thứ tự hiển thị')),
            ],
            options={
                'verbose_name': 'Danh mục tiện ích',
                'verbose_name_plural': 'Danh mục tiện ích',
                'ordering': ['order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='RestaurantAmenity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_available', models.BooleanField(default=True, verbose_name='Có sẵn')),
                ('note', models.TextField(blank=True, help_text='Vd: Wifi 24h, Máy lạnh từ 10:00 - 23:00, v.v.', verbose_name='Ghi chú')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='restaurant_amenities', to='restaurants.amenitycategory', verbose_name='Danh mục tiện ích')),
                ('restaurant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='amenities', to='restaurants.restaurant', verbose_name='Quán ăn')),
            ],
            options={
                'verbose_name': 'Tiện ích quán ăn',
                'verbose_name_plural': 'Tiện ích quán ăn',
                'ordering': ['category__order'],
                'unique_together': {('restaurant', 'category')},
            },
        ),
    ]
