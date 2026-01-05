"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from pages.views import ComponentPreviewView, PreviewPopupView

from .views import HealthCheckView

# Customize Django Admin
admin.site.site_header = "Innovate To Grow Admin"
admin.site.site_title = "I2G Admin"
admin.site.index_title = "Welcome to I2G Admin"

urlpatterns = [
    # health check endpoint
    path("health/", HealthCheckView.as_view(), name="health-check"),
    # admin preview popup for live editing
    path("admin/preview-popup/", PreviewPopupView.as_view(), name="admin-preview-popup"),
    # component preview popup for live editing
    path("admin/component-preview/", ComponentPreviewView.as_view(), name="admin-component-preview"),
    # admin site
    path("admin/", admin.site.urls),
    # pages
    path("pages/", include("pages.urls")),
    # layout (menus, footer)
    path("layout/", include("layout.urls")),
    # notify (verification + notifications)
    path("notify/", include("notify.urls")),
    # mobile id domain
    path("api/mobileid/", include("mobileid.urls")),
    # events (proxy removes /api prefix)
    path("events/", include("events.urls")),
    # ckeditor 5
    path("ckeditor5/", include("django_ckeditor_5.urls")),
    # authn
    path("authn/", include("authn.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
