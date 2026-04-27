from datetime import datetime, timedelta

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.services import get_season_report, get_user_season_or_404
from core.models import AgronomistAssignment, Season


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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def seasons_by_year(request):
    year = request.GET.get("year")
    if not year:
        return Response({"error": "year is required"}, status=400)

    try:
        year = int(year)
    except ValueError:
        return Response({"error": "year must be an integer"}, status=400)

    qs = Season.objects.filter(year=year)
    if request.user.role == "agronomist":
        owner_id = request.GET.get("owner_id") or request.session.get("active_owner_id")
        assigned_owner_ids = AgronomistAssignment.objects.filter(
            agronomist=request.user
        ).values_list("owner_id", flat=True)
        qs = qs.filter(owner_id__in=assigned_owner_ids)
        if owner_id:
            qs = qs.filter(owner_id=owner_id)
    else:
        qs = qs.filter(owner=request.user)

    return Response({
        "seasons": [
            {
                "id": season.id,
                "name": str(season),
                "year": season.year,
                "owner_id": season.owner_id,
                "start_date": season.start_date.isoformat(),
                "end_date": season.end_date.isoformat(),
            }
            for season in qs.order_by("start_date")
        ]
    })
