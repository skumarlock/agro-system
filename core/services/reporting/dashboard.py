from core.models import User
from core.services.analytics import (
    calculate_user_total_cost,
    get_user_fields_count,
    get_user_operations_count,
    get_user_resources_summary,
)


def get_dashboard_data(user: User) -> dict:
    return {
        "total_cost": calculate_user_total_cost(user),
        "fields_count": get_user_fields_count(user),
        "operations_count": get_user_operations_count(user),
        "resources": get_user_resources_summary(user),
    }
