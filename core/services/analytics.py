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


from django.utils.timezone import now

def get_base_queryset(user: User, period="all", month=None, year=None, season_id=None):
    qs = OperationResource.objects.filter(
        operation__field_crop__field__owner=user
    )

    today = now().date()

    if period == "month":
        if month and year:
            qs = qs.filter(
                operation__date__month=month,
                operation__date__year=year
            )
        else:
            qs = qs.filter(
                operation__date__month=today.month,
                operation__date__year=today.year
            )

    elif period == "season":
        if season_id:
            qs = qs.filter(
                operation__field_crop__season_id=season_id
            )
        else:
            qs = qs.filter(
            operation__field_crop__season__start_date__lte=today,
            operation__field_crop__season__end_date__gte=today,
        )

    return qs

def calculate_user_total_cost(user: User, period="all", month=None, year=None, season_id=None) -> Decimal:
    qs = get_base_queryset(user, period, month, year, season_id)

    result = qs.annotate(
        total=COST_EXPR,
    ).aggregate(total_cost=Sum("total"))

    return result["total_cost"] or ZERO_DECIMAL

def calculate_season_total_cost(season: Season, user: User) -> Decimal:
    result = OperationResource.objects.filter(
        operation__field_crop__season=season,
        operation__field_crop__field__owner=user,
    ).annotate(
        total=COST_EXPR,
    ).aggregate(total_cost=Sum("total"))

    return result["total_cost"] if result["total_cost"] is not None else ZERO_DECIMAL


def get_user_fields_count(user: User, period="all", month=None, year=None, season_id=None):
    qs = get_base_queryset(user, period, month, year, season_id)
    return qs.values("operation__field_crop__field").distinct().count()


def get_user_operations_count(user: User, period="all", month=None, year=None, season_id=None) -> int:
    qs = get_base_queryset(user, period, month, year, season_id)

    return qs.values("operation").distinct().count()


def get_user_resources_summary(user: User, period="all", month=None, year=None, season_id=None):
    qs = get_base_queryset(user, period, month, year, season_id)

    queryset = qs.values("resource__name", "resource__type").annotate(
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
            "type": item["resource__type"],
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
