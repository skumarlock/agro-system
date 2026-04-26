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


def _get_owner_filter(user: User):
    """Return a dict of filter kwargs to scope OperationResource to the correct owner(s)."""
    if user.role == "agronomist":
        from core.models import AgronomistAssignment
        owner_ids = AgronomistAssignment.objects.filter(
            agronomist=user
        ).values_list("owner_id", flat=True)
        return {"operation__field_crop__field__owner_id__in": list(owner_ids)}
    return {"operation__field_crop__field__owner": user}


def get_base_queryset(user: User, period="all", month=None, year=None,
                      from_date=None, to_date=None):
    qs = OperationResource.objects.filter(**_get_owner_filter(user))

    today = now().date()

    if from_date and to_date:
        qs = qs.filter(operation__date__gte=from_date, operation__date__lte=to_date)
    elif period == "month":
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
    elif period == "year":
        y = int(year) if year else today.year
        qs = qs.filter(operation__date__year=y)

    return qs

def calculate_user_total_cost(user: User, period="all", month=None, year=None,
                              from_date=None, to_date=None) -> Decimal:
    qs = get_base_queryset(user, period, month, year, from_date=from_date, to_date=to_date)
    result = qs.annotate(total=COST_EXPR).aggregate(total_cost=Sum("total"))
    return result["total_cost"] or ZERO_DECIMAL

def calculate_season_total_cost(season: Season, user: User) -> Decimal:
    qs = OperationResource.objects.filter(operation__field_crop__season=season)
    if user.role == "agronomist":
        from core.models import AgronomistAssignment
        owner_ids = AgronomistAssignment.objects.filter(agronomist=user).values_list("owner_id", flat=True)
        qs = qs.filter(operation__field_crop__field__owner_id__in=owner_ids)
    else:
        qs = qs.filter(operation__field_crop__field__owner=user)
    result = qs.annotate(total=COST_EXPR).aggregate(total_cost=Sum("total"))
    return result["total_cost"] if result["total_cost"] is not None else ZERO_DECIMAL


def get_user_fields_count(user: User, period="all", month=None, year=None,
                          from_date=None, to_date=None):
    qs = get_base_queryset(user, period, month, year, from_date=from_date, to_date=to_date)
    return qs.values("operation__field_crop__field").distinct().count()


def get_user_operations_count(user: User, period="all", month=None, year=None,
                              from_date=None, to_date=None) -> int:
    qs = get_base_queryset(user, period, month, year, from_date=from_date, to_date=to_date)
    return qs.values("operation").distinct().count()


def get_user_resources_summary(user: User, period="all", month=None, year=None,
                               from_date=None, to_date=None):
    qs = get_base_queryset(user, period, month, year, from_date=from_date, to_date=to_date)

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
    qs = FieldCrop.objects.filter(season=season)
    if user.role == "agronomist":
        from core.models import AgronomistAssignment
        owner_ids = AgronomistAssignment.objects.filter(agronomist=user).values_list("owner_id", flat=True)
        qs = qs.filter(field__owner_id__in=owner_ids)
    else:
        qs = qs.filter(field__owner=user)
    return qs.values("field_id").distinct().count()


def get_season_operations_count(season: Season, user: User) -> int:
    qs = Operation.objects.filter(field_crop__season=season)
    if user.role == "agronomist":
        from core.models import AgronomistAssignment
        owner_ids = AgronomistAssignment.objects.filter(agronomist=user).values_list("owner_id", flat=True)
        qs = qs.filter(field_crop__field__owner_id__in=owner_ids)
    else:
        qs = qs.filter(field_crop__field__owner=user)
    return qs.count()


def get_season_resources_summary(season: Season, user: User) -> list[dict]:
    qs = OperationResource.objects.filter(operation__field_crop__season=season)
    if user.role == "agronomist":
        from core.models import AgronomistAssignment
        owner_ids = AgronomistAssignment.objects.filter(agronomist=user).values_list("owner_id", flat=True)
        qs = qs.filter(operation__field_crop__field__owner_id__in=owner_ids)
    else:
        qs = qs.filter(operation__field_crop__field__owner=user)

    queryset = qs.values("resource__type").annotate(
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
