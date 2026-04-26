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
    from_date=None,
    to_date=None,
) -> dict:
    return {
        "total_cost": calculate_user_total_cost(
            user, period=period, month=month, year=year,
            from_date=from_date, to_date=to_date
        ),
        "fields_count": get_user_fields_count(
            user, period=period, month=month, year=year,
            from_date=from_date, to_date=to_date
        ),
        "operations_count": get_user_operations_count(
            user, period=period, month=month, year=year,
            from_date=from_date, to_date=to_date
        ),
        "resources": get_user_resources_summary(
            user, period=period, month=month, year=year,
            from_date=from_date, to_date=to_date
        ),
    }
