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


def get_field_crop_report(field_crop: FieldCrop) -> dict:
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
        "total_cost": calculate_field_crop_total_cost(field_crop),
        "cost_per_hectare": calculate_cost_per_hectare(field_crop),
        "resources": get_field_crop_resources(field_crop),
    }


def get_season_report(season: Season, user: User) -> dict:
    return {
        "season_id": season.id,
        "season": {
            "id": season.id,
            "name": season.name,
            "year": season.year,
        },
        "total_cost": calculate_season_total_cost(season, user),
        "fields_count": get_season_fields_count(season, user),
        "operations_count": get_season_operations_count(season, user),
        "resources": get_season_resources_summary(season, user),
    }

def get_field_crops_reports(user):
    field_crops = (
        FieldCrop.objects.filter(field__owner=user)
        .select_related("field", "crop", "season")
        .order_by("id")
    )

    return [get_field_crop_report(fc) for fc in field_crops]