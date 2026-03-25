from django.urls import path

from .views import SponsorListAPIView

app_name = "sponsors"

urlpatterns = [
    path("", SponsorListAPIView.as_view(), name="sponsor-list"),
]
