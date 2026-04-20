from collections import defaultdict
from decimal import Decimal

from core.models import Operation


ZERO_DECIMAL = Decimal("0")


def calculate_operation_cost(operation: Operation) -> Decimal:
    total_cost = ZERO_DECIMAL

    for operation_resource in operation.operation_resources.select_related("resource"):
        total_cost += operation_resource.quantity * operation_resource.resource.cost_per_unit

    return total_cost


def get_operation_resources_summary(operation: Operation) -> dict[str, Decimal]:
    summary = defaultdict(lambda: ZERO_DECIMAL)

    for operation_resource in operation.operation_resources.select_related("resource"):
        resource_type = operation_resource.resource.type
        summary[resource_type] += operation_resource.quantity

    return dict(summary)
