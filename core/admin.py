from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Field, Crop, Season,
    FieldCrop, Operation, Resource, OperationResource
)

# =====================
# USER
# =====================
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User

    list_display = ("username", "email", "role", "is_staff")

    fieldsets = UserAdmin.fieldsets + (
        ("Дополнительно", {"fields": ("role",)}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Дополнительно", {"fields": ("email", "role")}),
    )


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