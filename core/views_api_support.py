from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.services import get_season_report, get_user_season_or_404


class SeasonReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        season = get_user_season_or_404(request.user, pk)
        return Response(get_season_report(season, request.user))
