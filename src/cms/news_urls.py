from django.urls import path

from cms.views.news import NewsDetailAPIView, NewsListAPIView

app_name = "news"

urlpatterns = [
    path("", NewsListAPIView.as_view(), name="news-list"),
    path("<uuid:pk>/", NewsDetailAPIView.as_view(), name="news-detail"),
]
