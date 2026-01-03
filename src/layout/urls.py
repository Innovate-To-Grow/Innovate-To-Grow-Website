from django.urls import path

from .views import LayoutAPIView

app_name = "layout"

urlpatterns = [
    # combined layout data (menus and footer)
    path("", LayoutAPIView.as_view(), name="layout-data"),
]
