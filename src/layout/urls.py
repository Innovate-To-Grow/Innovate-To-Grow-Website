from django.urls import path
from .views import MenuAPIView, FooterContentAPIView

app_name = "layout"

urlpatterns = [
    # menu list
    path("menus/", MenuAPIView.as_view(), name="menu-list"),

    # footer content
    path("footer/", FooterContentAPIView.as_view(), name="footer-content"),
]
