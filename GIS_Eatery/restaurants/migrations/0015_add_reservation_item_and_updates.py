# Generated migration for ReservationItem model and Reservation updates

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0014_alter_dish_id_alter_feedback_id_alter_pickuporder_id_and_more'),
    ]

    operations = [
        # Thêm các trường mới vào Reservation
        migrations.AddField(
            model_name='reservation',
            name='customer_phone',
            field=models.CharField(blank=True, max_length=20, verbose_name='Số điện thoại'),
        ),
        migrations.AddField(
            model_name='reservation',
            name='note',
            field=models.TextField(blank=True, verbose_name='Ghi chú'),
        ),
        migrations.AddField(
            model_name='reservation',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        
        # Tạo model ReservationItem
        migrations.CreateModel(
            name='ReservationItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(default=1, verbose_name='Số lượng')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('dish', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reservation_items', to='restaurants.dish', verbose_name='Món ăn')),
                ('reservation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='restaurants.reservation', verbose_name='Đơn đặt bàn')),
            ],
            options={
                'verbose_name': 'Chi tiết đơn đặt bàn',
                'verbose_name_plural': 'Chi tiết đơn đặt bàn',
            },
        ),
        
        # Thêm unique constraint
        migrations.AddConstraint(
            model_name='reservationitem',
            constraint=models.UniqueConstraint(fields=['reservation', 'dish'], name='unique_reservation_dish'),
        ),
    ]
