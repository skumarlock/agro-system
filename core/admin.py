from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Field, Crop, Season,
    FieldCrop, Operation, OperationType, Resource, OperationResource, AgronomistAssignment, ResourcePrice
)

# =====================
# USER
# =====================
class WorkerInline(admin.TabularInline):
    model = User
    fk_name = "owner"
    extra = 0

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(role="worker")


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User

    list_display = ("username", "email", "role", "owner", "is_staff")
    list_filter = ("role", "owner")

    fieldsets = UserAdmin.fieldsets + (
        ("Дополнительно", {"fields": ("role", "owner")}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Дополнительно", {"fields": ("email", "role", "owner")}),
    )

    def get_inlines(self, request, obj):
        if obj and obj.role == "owner":
            return [WorkerInline]
        return []


# =====================
# FIELD
# =====================
@admin.register(Field)
class FieldAdmin(admin.ModelAdmin):
    list_display = ("name", "area", "owner", "location")
    list_filter = ("owner",)
    search_fields = ("name",)


# =====================
# CROP
# =====================
@admin.register(Crop)
class CropAdmin(admin.ModelAdmin):
    list_display = ("name", "category")


# =====================
# SEASON
# =====================
@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ("name", "year", "start_date", "end_date")


# =====================
# INLINE
# =====================
class OperationResourceInline(admin.TabularInline):
    model = OperationResource
    extra = 1


# =====================
# OPERATION
# =====================
@admin.register(OperationType)
class OperationTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "owner")
    list_filter = ("owner",)
    search_fields = ("name",)


@admin.register(Operation)
class OperationAdmin(admin.ModelAdmin):
    list_display = ("type", "date", "status", "field_crop", "performed_by")
    list_filter = ("type", "status")
    inlines = [OperationResourceInline]


# =====================
# FIELD CROP
# =====================
@admin.register(FieldCrop)
class FieldCropAdmin(admin.ModelAdmin):
    list_display = ("field", "crop", "season", "status")


# =====================
# RESOURCE
# =====================
@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "unit", "cost_per_unit")


# =====================
# OPERATION RESOURCE
# =====================
@admin.register(OperationResource)
class OperationResourceAdmin(admin.ModelAdmin):
    list_display = ("operation", "resource", "quantity")


@admin.register(AgronomistAssignment)
class AgronomistAssignmentAdmin(admin.ModelAdmin):
    list_display = ("owner", "agronomist", "created_at")
    list_filter = ("owner", "agronomist")


@admin.register(ResourcePrice)
class ResourcePriceAdmin(admin.ModelAdmin):
    list_display = ("owner", "resource", "price", "updated_at")
    list_filter = ("owner", "resource__type")
    search_fields = ("resource__name",)
