from collections import defaultdict
from decimal import Decimal
from django.db.models.functions import Coalesce

from django.db.models import DecimalField, ExpressionWrapper, F, Sum

from core.models import FieldCrop, Operation, OperationResource, Season, User


ZERO_DECIMAL = Decimal("0")

COST_EXPR = ExpressionWrapper(
    F("quantity") * Coalesce(
        F("price_per_unit"),
        F("resource__cost_per_unit")
    ),
    output_field=DecimalField(max_digits=12, decimal_places=2),
)


def calculate_user_total_cost(user: User) -> Decimal:
    result = OperationResource.objects.filter(
        operation__field_crop__field__owner=user,
    ).annotate(
        total=COST_EXPR,
    ).aggregate(total_cost=Sum("total"))

    return result["total_cost"] if result["total_cost"] is not None else ZERO_DECIMAL


def calculate_season_total_cost(season: Season, user: User) -> Decimal:
    result = OperationResource.objects.filter(
        operation__field_crop__season=season,
        operation__field_crop__field__owner=user,
    ).annotate(
        total=COST_EXPR,
    ).aggregate(total_cost=Sum("total"))

    return result["total_cost"] if result["total_cost"] is not None else ZERO_DECIMAL


def get_user_fields_count(user: User) -> int:
    return user.fields.count()


def get_user_operations_count(user: User) -> int:
    return Operation.objects.filter(field_crop__field__owner=user).count()


def get_user_resources_summary(user: User):
    qs = OperationResource.objects.filter(
        operation__field_crop__field__owner=user
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


def get_season_fields_count(season: Season, user: User) -> int:
    return FieldCrop.objects.filter(
        season=season,
        field__owner=user,
    ).values("field_id").distinct().count()


def get_season_operations_count(season: Season, user: User) -> int:
    return Operation.objects.filter(
        field_crop__season=season,
        field_crop__field__owner=user,
    ).count()


def get_season_resources_summary(season: Season, user: User) -> list[dict]:
    queryset = OperationResource.objects.filter(
        operation__field_crop__season=season,
        operation__field_crop__field__owner=user
    ).values(
        "resource__type"
    ).annotate(
        total_quantity=Sum("quantity"),
        total_cost=Sum(COST_EXPR),
    )

    return [
        {
            "name": item["resource__type"],
            "quantity": item["total_quantity"] or ZERO_DECIMAL,
            "cost": item["total_cost"] or ZERO_DECIMAL,
        }
        for item in queryset
    ]
