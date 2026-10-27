from django.contrib import admin
from django.urls import include, path

handler404 = "newsletters.views.public.not_found"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("newsletters.urls")),
]
