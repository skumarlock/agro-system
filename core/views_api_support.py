from datetime import datetime, timedelta

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.services import get_season_report, get_user_season_or_404


class SeasonReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        season = get_user_season_or_404(request.user, pk)
        return Response(get_season_report(season, request.user))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ai_plan_mock(request):
    """
    Mock AI plan endpoint.
    Returns: { "dates": ["YYYY-MM-DD", ...] }
    Accepts: ?start=YYYY-MM-DD&end=YYYY-MM-DD&type=<operation_type>
    """
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")

    if not start_str or not end_str:
        return Response({"error": "start and end dates are required"}, status=400)

    try:
        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
    except ValueError:
        return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)

    if end_date < start_date:
        return Response({"error": "end must be after start"}, status=400)

    # Mock AI logic: suggest up to 5 dates spaced evenly across the range
    delta = (end_date - start_date).days
    step = max(delta // 5, 7)  # at least weekly
    dates = []
    cur = start_date
    while cur <= end_date and len(dates) < 5:
        dates.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=step)

    return Response({"dates": dates})
