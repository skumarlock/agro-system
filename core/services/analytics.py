from decimal import Decimal

from core.models import FieldCrop, Season, User
from core.services.field_crop import calculate_field_crop_total_cost


ZERO_DECIMAL = Decimal("0")


def calculate_user_total_cost(user: User) -> Decimal:
    total_cost = ZERO_DECIMAL

    field_crops = (
        FieldCrop.objects.filter(field__owner=user)
        .select_related("field", "crop", "season")
        .prefetch_related("operations__operation_resources__resource")
    )

    for field_crop in field_crops:
        total_cost += calculate_field_crop_total_cost(field_crop)

    return total_cost


def calculate_season_total_cost(season: Season, user: User) -> Decimal:
    total_cost = ZERO_DECIMAL

    field_crops = season.field_crops.select_related("field", "crop", "season").prefetch_related(
        "operations__operation_resources__resource",
    ).filter(field__owner=user)

    for field_crop in field_crops:
        total_cost += calculate_field_crop_total_cost(field_crop)

    return total_cost
