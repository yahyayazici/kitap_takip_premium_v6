from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("yonetim/", include("takip.yonetim_urls")),
    path("", include("takip.urls")),
]