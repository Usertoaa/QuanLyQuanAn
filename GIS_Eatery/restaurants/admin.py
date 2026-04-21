from django.contrib.gis import admin
from .models import Dish, Restaurant, Table, Reservation, ReservationItem, AmenityCategory, RestaurantAmenity


class DishInline(admin.TabularInline):
    model = Dish
    extra = 1


class ReservationItemInline(admin.TabularInline):
    model = ReservationItem
    extra = 1
    readonly_fields = ('created_at',)


class RestaurantAmenityInline(admin.TabularInline):
    model = RestaurantAmenity
    extra = 1


@admin.register(Restaurant)
class RestaurantAdmin(admin.GISModelAdmin):
   list_display = ('name', 'address', 'district', 'created_at')
   search_fields = ('name', 'address')
   list_filter = ('district',)
    
   inlines = [DishInline, RestaurantAmenityInline]

@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ('restaurant', 'table_number', 'capacity', 'is_available')
    list_filter = ('restaurant', 'is_available')

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('customer_name', 'get_restaurant', 'table', 'booking_time', 'number_of_people', 'status', 'get_items_count')
    list_filter = ('booking_time', 'status')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ReservationItemInline]

    def get_restaurant(self, obj):
        return obj.table.restaurant.name
    get_restaurant.short_description = 'Quán ăn'
    
    def get_items_count(self, obj):
        return obj.get_items_count() or 'Không'
    get_items_count.short_description = 'Số lượng món'


@admin.register(ReservationItem)
class ReservationItemAdmin(admin.ModelAdmin):
    list_display = ('get_reservation_customer', 'dish', 'quantity', 'get_subtotal')
    list_filter = ('created_at',)
    search_fields = ('reservation__customer_name', 'dish__name')
    readonly_fields = ('created_at', 'get_subtotal')
    
    def get_reservation_customer(self, obj):
        return f"{obj.reservation.customer_name} - {obj.reservation.table.restaurant.name}"
    get_reservation_customer.short_description = 'Khách / Quán'


@admin.register(AmenityCategory)
class AmenityCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'order')
    list_editable = ('order',)
    list_filter = ('order',)
    search_fields = ('name',)
    fieldsets = (
        ('Thông tin', {
            'fields': ('name', 'icon', 'order')
        }),
        ('Chi tiết', {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
    )


@admin.register(RestaurantAmenity)
class RestaurantAmenityAdmin(admin.ModelAdmin):
    list_display = ('restaurant', 'category', 'is_available', 'note')
    list_filter = ('category', 'is_available', 'restaurant')
    search_fields = ('restaurant__name', 'category__name')
    fieldsets = (
        ('Thông tin', {
            'fields': ('restaurant', 'category', 'is_available')
        }),
        ('Ghi chú', {
            'fields': ('note',)
        }),
    )