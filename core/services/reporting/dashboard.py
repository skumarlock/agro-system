from core.models import User
from core.services.analytics import (
    calculate_user_total_cost,
    get_user_fields_count,
    get_user_operations_count,
    get_user_resources_summary,
)


def get_dashboard_data(
    user: User,
    period="all",
    month=None,
    year=None,
    season_id=None
) -> dict:
    return {
        "total_cost": calculate_user_total_cost(
            user, period=period, month=month, year=year, season_id=season_id
        ),
        "fields_count": get_user_fields_count(
            user, period=period, month=month, year=year, season_id=season_id
        ),
        "operations_count": get_user_operations_count(
            user, period=period, month=month, year=year, season_id=season_id
        ),
        "resources": get_user_resources_summary(
            user, period=period, month=month, year=year, season_id=season_id
        ),
    }
