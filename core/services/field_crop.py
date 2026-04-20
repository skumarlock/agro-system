from decimal import Decimal
from django.db.models import F, Sum, DecimalField, ExpressionWrapper
from core.models import FieldCrop, OperationResource, Operation

ZERO_DECIMAL = Decimal("0")

COST_EXPR = ExpressionWrapper(
    F("quantity") * F("resource__cost_per_unit"),
    output_field=DecimalField(max_digits=12, decimal_places=2)
)

def calculate_field_crop_total_cost(field_crop: FieldCrop) -> Decimal:
    qs = OperationResource.objects.filter(
        operation__field_crop=field_crop
    )

    result = qs.annotate(
        total=COST_EXPR
    ).aggregate(total_cost=Sum("total"))

    return result["total_cost"] or ZERO_DECIMAL


def get_field_crop_resources(field_crop: FieldCrop) -> dict[str, Decimal]:
    qs = OperationResource.objects.filter(
        operation__field_crop=field_crop
    )

    queryset = qs.values("resource__type").annotate(
        total_quantity=Sum("quantity")
    )

    return {
        item["resource__type"]: item["total_quantity"] if item["total_quantity"] is not None else ZERO_DECIMAL
        for item in queryset
    }


def get_field_crop_operations_count(field_crop: FieldCrop) -> int:
    return Operation.objects.filter(field_crop=field_crop).count()


def calculate_cost_per_hectare(field_crop: FieldCrop) -> Decimal:
    area = field_crop.field.area

    if not area:
        return ZERO_DECIMAL

    total_cost = calculate_field_crop_total_cost(field_crop)
    return total_cost / area
