from django.urls import path

from .views import SheetsDataView, SheetsRefreshView

app_name = "sheets"

urlpatterns = [
    path("<slug:slug>/", SheetsDataView.as_view(), name="sheets-data"),
    path("<slug:slug>/refresh/", SheetsRefreshView.as_view(), name="sheets-refresh"),
]
