from django.urls import path
from .views import PageRetrieveAPIView, PageListAPIView, HomePageAPIView

app_name = "pages"

urlpatterns = [
    # home page
    path("home/", HomePageAPIView.as_view(), name="home-page"),

    # pages list (for menu editor)
    path("pages/", PageListAPIView.as_view(), name="page-list"),

    # page detail
    path("pages/<slug:slug>/", PageRetrieveAPIView.as_view(), name="page-retrieve"),
]
