from core.models import User
from core.services.analytics import (
    calculate_user_total_cost,
    get_user_fields_count,
    get_user_operations_count,
    get_user_resources_summary,
)


def get_dashboard_data(user: User, period="all") -> dict:
    return {
        "total_cost": calculate_user_total_cost(user, period=period),
        "fields_count": get_user_fields_count(user, period=period),
        "operations_count": get_user_operations_count(user, period=period),
        "resources": get_user_resources_summary(user, period=period),
    }
