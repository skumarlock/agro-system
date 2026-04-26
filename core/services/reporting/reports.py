from core.models import FieldCrop, Season, User
from core.services.analytics import (
    calculate_season_total_cost,
    get_season_fields_count,
    get_season_operations_count,
    get_season_resources_summary,
)
from core.services.field_crop import (
    calculate_cost_per_hectare,
    calculate_field_crop_total_cost,
    get_field_crop_operations_count,
    get_field_crop_resources,
)


def get_field_crop_report(field_crop: FieldCrop, include_finances=True) -> dict:
    resources = get_field_crop_resources(field_crop)
    total_cost = calculate_field_crop_total_cost(field_crop)
    cost_per_hectare = calculate_cost_per_hectare(field_crop)

    if not include_finances:
        total_cost = None
        cost_per_hectare = None

        for r in resources:
            r["cost"] = None
            r["total"] = None
    return {
    "field_crop_id": field_crop.id,
    "field": {
        "id": field_crop.field.id,
        "name": field_crop.field.name,
    },
    "crop": {
        "id": field_crop.crop.id,
        "name": field_crop.crop.name,
    },
    "season": {
        "id": field_crop.season.id,
        "name": field_crop.season.name,
        "year": field_crop.season.year,
    },
    "status": field_crop.status,
    "operations_count": get_field_crop_operations_count(field_crop),

    "total_cost": total_cost,
    "cost_per_hectare": cost_per_hectare,

    "resources": resources,
}


def get_season_report(season: Season, user: User, include_finances=True) -> dict:
    total_cost = calculate_season_total_cost(season, user)
    resources = get_season_resources_summary(season, user)

    if not include_finances:
        total_cost = None
        for resource in resources:
            resource["cost"] = None

    return {
        "season_id": season.id,
        "season": {
            "id": season.id,
            "name": season.name,
            "year": season.year,
        },
        "total_cost": total_cost,
        "fields_count": get_season_fields_count(season, user),
        "operations_count": get_season_operations_count(season, user),
        "resources": resources,
    }

def get_field_crops_reports(user):
    qs = FieldCrop.objects.select_related("field", "crop", "season").order_by("id")
    if user.role == "agronomist":
        from core.models import AgronomistAssignment
        owner_ids = AgronomistAssignment.objects.filter(
            agronomist=user
        ).values_list("owner_id", flat=True)
        qs = qs.filter(field__owner_id__in=owner_ids)
    else:
        qs = qs.filter(field__owner=user)
    return [get_field_crop_report(fc, include_finances=True) for fc in qs]
