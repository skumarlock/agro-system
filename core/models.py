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
    
    def clean(self):
        # owner не может иметь owner
        if self.role == "owner" and self.owner is not None:
            raise ValidationError("Владелец не может иметь владельца")
        # worker обязан иметь owner
        if self.role == "worker" and self.owner is None:
            raise ValidationError("Работник должен иметь владельца")
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Season(TimeStampedModel):
    name = models.CharField(max_length=50)
    year = models.PositiveIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    owner = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="seasons",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-year", "name"]
        unique_together = ("owner", "name", "start_date", "end_date")
        indexes = [
            models.Index(fields=["owner", "year"], name="core_season_owner_year_idx"),
        ]

    def clean(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError("Дата окончания должна быть позже даты начала")

        if self.start_date:
            self.year = self.start_date.year

        if not self.owner_id or not self.start_date or not self.end_date:
            return

        qs = Season.objects.filter(owner=self.owner).exclude(pk=self.pk)
        if qs.filter(name=self.name, year=self.year).exists():
            raise ValidationError("Сезон уже существует")

        if qs.filter(
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        ).exists():
            raise ValidationError("Сезон пересекается с существующим сезоном")

    def save(self, *args, **kwargs):
        if self.start_date:
            self.year = self.start_date.year
        self.full_clean()
        super().save(*args, **kwargs)

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
        PLANNED = "запланировано", "Запланировано"
        ACTIVE = "активно", "Активно"
        HARVESTED = "собран", "Собрано"

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
            raise ValidationError("Дата сбора урожая не может быть раньше даты посадки")
    
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

    def get_computed_status(self) -> str:
        from core.models import Operation

        today = timezone.now().date()

        if today < self.planting_date:
            return self.Status.PLANNED

        if self.harvest_date and today > self.harvest_date:
            return self.Status.HARVESTED

        if self.planting_date <= today and (
            not self.harvest_date or today <= self.harvest_date
        ):
            return self.Status.ACTIVE

        ops = Operation.objects.filter(
            field_crop__field=self.field,
            field_crop__crop=self.crop,
            field_crop__season=self.season,
        )
        if ops.exists():
            if ops.filter(status="done").exists():
                return self.Status.ACTIVE
            return self.Status.PLANNED

        return self.Status.ACTIVE

    def __str__(self):
        return f"{self.field} - {self.crop} ({self.season})"


class OperationType(TimeStampedModel):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="operation_types",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]
        unique_together = ("owner", "name")

    def __str__(self):
        return self.name


LEGACY_OPERATION_TYPE_MAP = {
    "полив": "Полив",
    "посадка": "Посадка",
    "удобрение": "Удобрение",
    "сбор урожая": "Сбор урожая",
}


class OperationManager(models.Manager):
    def create(self, **kwargs):
        type_value = kwargs.get("type")
        if isinstance(type_value, str):
            type_name = LEGACY_OPERATION_TYPE_MAP.get(type_value, type_value)
            kwargs["type"], _ = OperationType.objects.get_or_create(
                owner=None,
                name=type_name,
            )
        return super().create(**kwargs)


class Operation(TimeStampedModel):
    class Type(models.TextChoices):
        WATERING = "полив", "Полив"
        PLANTING = "посадка", "Посадка"
        FERTILIZING = "удобрение", "Удобрение"
        HARVESTING = "сбор урожая", "Сбор урожая"

    class Status(models.TextChoices):
        PLANNED = "запланировано", "Запланировано"
        DONE = "выполнено", "Выполнено"

    field_crop = models.ForeignKey(
        FieldCrop,
        on_delete=models.CASCADE,
        related_name="operations",
    )
    type = models.ForeignKey(
        OperationType,
        on_delete=models.PROTECT,
        related_name="operations",
    )
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

    objects = OperationManager()

    def get_total_cost(self) -> Decimal:
        from core.services.operations import calculate_operation_cost

        return calculate_operation_cost(self)

    def __str__(self):
        return f"{self.type.name} - {self.date}"
    
    class Meta:
        indexes = [
            models.Index(fields=["field_crop"]),
            models.Index(fields=["date"]),
            models.Index(fields=["field_crop", "date"]),
        ]


class Resource(TimeStampedModel):
    class Type(models.TextChoices):
        WATER = "вода", "Вода"
        FERTILIZER = "питательная смесь", "Питательная смесь"
        FUEL = "топливо", "Топливо"
        SEED = "семена", "Семена"

    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=50)
    type = models.CharField(max_length=20, choices=Type.choices)
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.name


class ResourcePrice(TimeStampedModel):
    """Owner-specific price override for a resource."""
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="resource_prices",
    )
    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="prices",
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("owner", "resource")

    def __str__(self):
        return f"{self.resource.name} → {self.price} (owner: {self.owner})"


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
        if self.price_per_unit is None and self.resource_id:
            # Try owner-specific price first
            try:
                owner = self.operation.field_crop.field.owner
                rp = ResourcePrice.objects.filter(
                    owner=owner, resource_id=self.resource_id
                ).first()
                self.price_per_unit = rp.price if rp else Resource.objects.get(
                    pk=self.resource_id
                ).cost_per_unit
            except Exception:
                self.price_per_unit = Resource.objects.get(
                    pk=self.resource_id
                ).cost_per_unit
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ("operation", "resource")

    def __str__(self):
        return f"{self.operation} - {self.resource}"


class AgronomistAssignment(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="agronomist_links"
    )
    agronomist = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="client_links"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    can_view_finances = models.BooleanField(default=False)
    can_manage_operations = models.BooleanField(default=False)
    can_manage_seasons = models.BooleanField(default=False)
    can_manage_field_crops = models.BooleanField(default=False)

    def clean(self):
        if self.owner.role != "owner":
            raise ValidationError("Owner must have role 'owner'")

        if self.agronomist.role != "agronomist":
            raise ValidationError("Agronomist must have role 'agronomist'")

    def __str__(self):
        return f"{self.owner} ↔ {self.agronomist}"

class ExchangeRate(models.Model):
    currency = models.CharField(max_length=10)
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)
