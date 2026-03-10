"""Minimal URL conf for mail app tests, avoiding broken events imports."""

from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
]
