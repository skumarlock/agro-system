from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class User(AbstractUser, TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        WORKER = "worker", "Worker"
        ADMIN = "admin", "Admin"
        AGRONOMIST = "agronomist", "Agronomist"

    email = models.EmailField(unique=True, null=True, blank=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.OWNER
    )
    owner = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="workers"
    )


    def __str__(self):
        return self.username


class Season(TimeStampedModel):
    name = models.CharField(max_length=50)
    year = models.PositiveIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["-year", "name"]
        unique_together = ("name", "year")

    def __str__(self):
        return f"{self.name} {self.year}"


class Field(TimeStampedModel):
    name = models.CharField(max_length=255)
    area = models.DecimalField(max_digits=10, decimal_places=2)
    location = models.CharField(max_length=255)
    soil_type = models.CharField(max_length=100, blank=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="fields",
    )

    def __str__(self):
        return self.name


class Crop(TimeStampedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.name


class FieldCrop(TimeStampedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        HARVESTED = "harvested", "Harvested"

    field = models.ForeignKey(
        Field,
        on_delete=models.CASCADE,
        related_name="field_crops",
    )
    crop = models.ForeignKey(
        Crop,
        on_delete=models.CASCADE,
        related_name="field_crops",
    )
    season = models.ForeignKey(
        Season,
        on_delete=models.CASCADE,
        related_name="field_crops",
    )
    planting_date = models.DateField()
    harvest_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
    )

    def clean(self):
        if self.harvest_date and self.harvest_date < self.planting_date:
            raise ValidationError("Harvest date cannot be earlier than planting date")
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs) # при массовых вставках может быть медленно. 
        # сейчас это ок, но если будет много данных, то лучше убрать валидацию из модели и делать её на уровне формы или сериализатора
    
    class Meta:
        unique_together = ("field", "crop", "season")
        indexes = [
            models.Index(fields=["field"]),
            models.Index(fields=["season"]),
            models.Index(fields=["field", "season"]),
        ]

    def __str__(self):
        return f"{self.field} - {self.crop} ({self.season})"


class Operation(TimeStampedModel):
    class Type(models.TextChoices):
        WATERING = "watering", "Watering"
        PLANTING = "planting", "Planting"
        FERTILIZING = "fertilizing", "Fertilizing"
        HARVESTING = "harvesting", "Harvesting"

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        DONE = "done", "Done"

    field_crop = models.ForeignKey(
        FieldCrop,
        on_delete=models.CASCADE,
        related_name="operations",
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    date = models.DateField()
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
    )
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operations",
    )

    def get_total_cost(self) -> Decimal:
        from core.services.operations import calculate_operation_cost

        return calculate_operation_cost(self)

    def __str__(self):
        return f"{self.get_type_display()} - {self.date}"
    
    class Meta:
        indexes = [
            models.Index(fields=["field_crop"]),
            models.Index(fields=["date"]),
            models.Index(fields=["field_crop", "date"]),
        ]


class Resource(TimeStampedModel):
    class Type(models.TextChoices):
        WATER = "water", "Water"
        FERTILIZER = "fertilizer", "Fertilizer"
        FUEL = "fuel", "Fuel"
        SEED = "seed", "Seed"

    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=50)
    type = models.CharField(max_length=20, choices=Type.choices)
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.name


class OperationResource(TimeStampedModel):
    operation = models.ForeignKey(
        Operation,
        on_delete=models.CASCADE,
        related_name="operation_resources",
    )
    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="operation_resources",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    price_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,   # временно!
        blank=True
    )

    def save(self, *args, **kwargs):
        if self.price_per_unit is None:
            if self.resource_id:
                self.price_per_unit = Resource.objects.get(pk=self.resource_id).cost_per_unit
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ("operation", "resource")

    def __str__(self):
        return f"{self.operation} - {self.resource}"


class ExchangeRate(models.Model):
    currency = models.CharField(max_length=10)
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    