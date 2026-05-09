from django.urls import path

from cms.views.analytics import PageViewCreateView

app_name = "analytics"

urlpatterns = [
    path("pageview/", PageViewCreateView.as_view(), name="pageview-create"),
]
