from django.urls import path
from .views.sync_views import SyncToSheetAPIView, SyncFromSheetAPIView, FullSyncAPIView

app_name = "authn"

urlpatterns = [
    path('sync/to-sheet/', SyncToSheetAPIView.as_view(), name='sync-to-sheet'),
    path('sync/from-sheet/', SyncFromSheetAPIView.as_view(), name='sync-from-sheet'),
    path('sync/full/', FullSyncAPIView.as_view(), name='sync-full'),
]
