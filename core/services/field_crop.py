from collections import defaultdict
from decimal import Decimal

from core.models import FieldCrop
from core.services.operations import calculate_operation_cost, get_operation_resources_summary


ZERO_DECIMAL = Decimal("0")


def calculate_field_crop_total_cost(field_crop: FieldCrop) -> Decimal:
    total_cost = ZERO_DECIMAL

    operations = field_crop.operations.prefetch_related("operation_resources__resource")
    for operation in operations:
        total_cost += calculate_operation_cost(operation)

    return total_cost


def get_field_crop_resources(field_crop: FieldCrop) -> dict[str, Decimal]:
    resources_summary = defaultdict(lambda: ZERO_DECIMAL)

    operations = field_crop.operations.prefetch_related("operation_resources__resource")
    for operation in operations:
        operation_summary = get_operation_resources_summary(operation)
        for resource_type, quantity in operation_summary.items():
            resources_summary[resource_type] += quantity

    return dict(resources_summary)


def calculate_cost_per_hectare(field_crop: FieldCrop) -> Decimal:
    area = field_crop.field.area
    if not area:
        return ZERO_DECIMAL

    total_cost = calculate_field_crop_total_cost(field_crop)
    return total_cost / area
