from decimal import Decimal
from django.db.models import F, Sum, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce
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
        F("quantity") * Coalesce(
            F("price_per_unit"),
            F("resource__cost_per_unit")  # fallback
        ),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    ).aggregate(total_cost=Sum("total"))

    return result["total_cost"] or ZERO_DECIMAL


def get_user_operations(user, limit=None):
    qs = Operation.objects.select_related(
        "field_crop__field",
        "field_crop__crop",
        "type",
    ).prefetch_related(
        "operation_resources__resource"
    )

    if user.role == "owner":
        qs = qs.filter(field_crop__field__owner=user)
    elif user.role == "agronomist":
        from core.models import AgronomistAssignment
        owner_ids = AgronomistAssignment.objects.filter(
            agronomist=user
        ).values_list("owner_id", flat=True)
        qs = qs.filter(field_crop__field__owner_id__in=owner_ids)
    else:
        qs = qs.filter(performed_by=user)

    qs = qs.order_by("-date")

    if limit:
        qs = qs[:limit]

    return qs
