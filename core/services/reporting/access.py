from django.shortcuts import get_object_or_404

from core.models import FieldCrop, Season, User


def get_user_field_crop_or_404(user: User, pk: int) -> FieldCrop:
    qs = FieldCrop.objects.select_related("field", "crop", "season")

    if user.role == "owner":
        qs = qs.filter(field__owner=user)
    elif user.role == "agronomist":
        qs = qs.filter(field__owner__agronomist_links__agronomist=user)
    else:
        qs = qs.filter(operations__performed_by=user)

    return get_object_or_404(qs.distinct(), pk=pk)


def get_user_season_or_404(user: User, pk: int) -> Season:
    qs = Season.objects.all()

    if user.role == "owner":
        qs = qs.filter(owner=user)
    elif user.role == "agronomist":
        qs = qs.filter(owner__agronomist_links__agronomist=user)
    else:
        qs = qs.filter(
            field_crops__operations__performed_by=user
        )

    return get_object_or_404(qs.distinct(), pk=pk)
    
