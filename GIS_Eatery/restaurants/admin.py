from django.contrib.gis import admin
from .models import Dish, Restaurant, Table, Reservation


class DishInline(admin.TabularInline):
    model = Dish
    extra = 1

@admin.register(Restaurant)
class RestaurantAdmin(admin.GISModelAdmin):
   list_display = ('name', 'address', 'district', 'created_at')
   search_fields = ('name', 'address')
   list_filter = ('district',)
    
   inlines = [DishInline]

@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ('restaurant', 'table_number', 'capacity', 'is_available')
    list_filter = ('restaurant', 'is_available')

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('customer_name', 'get_restaurant', 'table', 'booking_time', 'number_of_people')
    list_filter = ('booking_time',)

    # Hàm phụ để hiển thị tên quán (vì Reservation nối với Table, không nối trực tiếp Restaurant)
    def get_restaurant(self, obj):
        return obj.table.restaurant.name
    get_restaurant.short_description = 'Quán ăn'