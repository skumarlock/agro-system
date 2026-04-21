from django.urls import path
from core.views import DashboardAPIView, FieldCropReportListAPIView
from core.views_api_support import SeasonReportAPIView


urlpatterns = [
    path('dashboard/', DashboardAPIView.as_view(), name='api-dashboard'),
    path('field-crops/', FieldCropReportListAPIView.as_view(), name='api-field-crops'),
    path('seasons/<int:pk>/', SeasonReportAPIView.as_view(), name='api-season-report'),

]