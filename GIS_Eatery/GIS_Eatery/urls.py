from django.urls import include
from django.contrib import admin
from django.urls import path
from django.conf.urls.static import static
from GIS_Eatery import settings

urlpatterns = [
    path('', include('restaurants.urls')),

    path('admin/', admin.site.urls),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)