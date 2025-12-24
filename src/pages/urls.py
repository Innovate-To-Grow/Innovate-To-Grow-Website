from django.urls import path
from .views import PageRetrieveAPIView, PageListAPIView, HomePageAPIView

app_name = "pages"

urlpatterns = [

    # pages list (for menu editor)
    path("", PageListAPIView.as_view(), name="page-list"),

    # home page
    path("home/", HomePageAPIView.as_view(), name="home-page"),

    # page detail
    path("<slug:slug>/", PageRetrieveAPIView.as_view(), name="page-retrieve"),
]
