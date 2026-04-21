from decimal import Decimal
from django.db.models import F, Sum, DecimalField, ExpressionWrapper
from core.models import FieldCrop, OperationResource, Operation
from django.db.models.functions import Coalesce

ZERO_DECIMAL = Decimal("0")

COST_EXPR = ExpressionWrapper(
    F("quantity") * Coalesce(
        F("price_per_unit"),
        F("resource__cost_per_unit")
    ),
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


def get_field_crop_resources(field_crop: FieldCrop):
    qs = OperationResource.objects.filter(
        operation__field_crop=field_crop
    )

    queryset = qs.values("resource__name").annotate(
        total_quantity=Sum("quantity"),
        total_cost=Sum(
            ExpressionWrapper(
                F("quantity") * Coalesce(
                    F("price_per_unit"),
                    F("resource__cost_per_unit")
                ),
                output_field=DecimalField(max_digits=14, decimal_places=2)
            )
        )
    )

    return [
        {
            "name": item["resource__name"],
            "quantity": item["total_quantity"] or ZERO_DECIMAL,
            "cost": item["total_cost"] or ZERO_DECIMAL,
        }
        for item in queryset
    ]


def get_field_crop_operations_count(field_crop: FieldCrop) -> int:
    return Operation.objects.filter(field_crop=field_crop).count()


def calculate_cost_per_hectare(field_crop: FieldCrop) -> Decimal:
    area = field_crop.field.area

    if not area:
        return ZERO_DECIMAL

    total_cost = calculate_field_crop_total_cost(field_crop)
    return total_cost / area
