from django.shortcuts import get_object_or_404

from core.models import FieldCrop, Season, User


def get_user_field_crop_or_404(user: User, pk: int) -> FieldCrop:
    return get_object_or_404(
        FieldCrop.objects.filter(field__owner=user).select_related("field", "crop", "season"),
        pk=pk,
    )


def get_user_season_or_404(user: User, pk: int) -> Season:
    return get_object_or_404(
        Season.objects.filter(field_crops__field__owner=user).distinct(),
        pk=pk,
    )
