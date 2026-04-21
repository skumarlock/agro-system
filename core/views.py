from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import FieldCrop, Season
from core.services import (
    get_dashboard_data,
    get_season_report,
    get_field_crops_reports,
)


class DashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_dashboard_data(request.user))


class FieldCropReportListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_field_crops_reports(request.user))


class SeasonReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        season = get_object_or_404(
            Season.objects.filter(owner=request.user),
            pk=pk,
        )
        return Response(get_season_report(season, request.user))
