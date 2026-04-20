from decimal import Decimal
from django.db.models import F, Sum, DecimalField, ExpressionWrapper

from core.models import Operation


ZERO_DECIMAL = Decimal("0")


def get_operation_resources_summary(operation: Operation) -> dict[str, Decimal]:
    qs = operation.operation_resources.all()

    queryset = qs.values("resource__type").annotate(
        total_quantity=Sum("quantity")
    )

    return {
        item["resource__type"]: item["total_quantity"] if item["total_quantity"] is not None else ZERO_DECIMAL
        for item in queryset
    }


def calculate_operation_cost(operation: Operation) -> Decimal:
    qs = operation.operation_resources.all()

    result = qs.annotate(
        total=ExpressionWrapper(
            F("quantity") * F("resource__cost_per_unit"),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
    ).aggregate(total_cost=Sum("total"))

    return result["total_cost"] or ZERO_DECIMAL