from django.urls import path
from core.views_ui import (
    dashboard_view,
    field_crop_list_view,
    field_crop_detail_view,
    season_report_view,
    update_rate_view,
)

urlpatterns = [
    path("dashboard/", dashboard_view, name="dashboard"),
    path("field-crops/", field_crop_list_view, name="field-crops"),
    path("field-crops/<int:pk>/", field_crop_detail_view, name="field-crop-detail"),
    path("seasons/<int:pk>/report/", season_report_view, name="season-report"),
    path("update-rate/", update_rate_view, name="update-rate"),
]