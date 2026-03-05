from django.urls import path

from .views import NewsListAPIView

app_name = "news"

urlpatterns = [
    path("", NewsListAPIView.as_view(), name="news-list"),
]
