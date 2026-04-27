from django.urls import path
from core.views import DashboardAPIView, FieldCropReportListAPIView
from core.views_api_support import SeasonReportAPIView, ai_plan_mock, seasons_by_year


urlpatterns = [
    path('dashboard/', DashboardAPIView.as_view(), name='api-dashboard'),
    path('field-crops/', FieldCropReportListAPIView.as_view(), name='api-field-crops'),
    path('seasons/', seasons_by_year, name='api-seasons-by-year'),
    path('seasons/<int:pk>/', SeasonReportAPIView.as_view(), name='api-season-report'),
    path('ai/plan/', ai_plan_mock, name='api-ai-plan'),
]
