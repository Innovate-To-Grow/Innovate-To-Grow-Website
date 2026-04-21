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

from authn.views.admin.login import AdminLoginView
from cms.views import LayoutAPIView, LayoutStylesheetView
from core.middleware import csp_report
from core.views import MaintenanceBypassView, robots_txt, root_index

# Customize Django Admin
admin.site.site_header = "Innovate To Grow Admin"
admin.site.site_title = "I2G Admin"
admin.site.index_title = "Welcome to I2G Admin"

urlpatterns = [
    # root → API index
    path("", root_index, name="root-index"),
    # robots.txt
    path("robots.txt", robots_txt, name="robots-txt"),
    # custom admin login (before admin.site.urls to override default)
    path("admin/login/", AdminLoginView.as_view(), name="admin-login"),
    # admin site
    path("admin/", admin.site.urls),
    # maintenance bypass
    path("maintenance/bypass/", MaintenanceBypassView.as_view(), name="maintenance-bypass"),
    # CSP violation report endpoint (logged to console)
    path("csp-report/", csp_report, name="csp-report"),
    # layout (menus, footer)
    path("layout/", LayoutAPIView.as_view(), name="layout-data"),
    # render-blocking stylesheet (linked from index.html to prevent FOUC)
    path("layout/styles.css", LayoutStylesheetView.as_view(), name="layout-styles"),
    # event
    path("event/", include("event.urls")),
    # news
    path("news/", include("cms.news_urls")),
    # projects
    path("projects/", include("projects.urls")),
    # ckeditor 5
    path("ckeditor5/", include("django_ckeditor_5.urls")),
    # cms
    path("cms/", include("cms.cms_urls")),
    # authn
    path("authn/", include("authn.urls")),
    # analytics
    path("analytics/", include("cms.analytics_urls")),
    # mail (magic login links)
    path("mail/", include("mail.urls")),
]

handler404 = "core.views.custom_404"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
