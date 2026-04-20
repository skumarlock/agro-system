from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import Crop, Field, FieldCrop, Operation, OperationResource, Resource, Season, User
from core.services.analytics import calculate_season_total_cost, calculate_user_total_cost
from core.services.field_crop import (
    calculate_cost_per_hectare,
    calculate_field_crop_total_cost,
    get_field_crop_resources,
)
from core.services.operations import calculate_operation_cost, get_operation_resources_summary


class BusinessLogicServicesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="farmer",
            password="testpass123",
            email="farmer@example.com",
        )
        self.second_user = User.objects.create_user(
            username="other_farmer",
            password="testpass123",
            email="other@example.com",
        )

        self.field = Field.objects.create(
            name="North field",
            area=Decimal("10.00"),
            location="Sector A",
            soil_type="Loam",
            owner=self.user,
        )
        self.second_field = Field.objects.create(
            name="South field",
            area=Decimal("5.00"),
            location="Sector B",
            soil_type="Clay",
            owner=self.second_user,
        )
        self.crop = Crop.objects.create(name="Wheat", description="Main crop", category="Grain")
        self.season = Season.objects.create(
            name="Spring",
            year=2026,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 5, 31),
        )
        self.field_crop = FieldCrop.objects.create(
            field=self.field,
            crop=self.crop,
            season=self.season,
            planting_date=date(2026, 3, 10),
            status=FieldCrop.Status.ACTIVE,
        )
        self.other_field_crop = FieldCrop.objects.create(
            field=self.second_field,
            crop=self.crop,
            season=self.season,
            planting_date=date(2026, 3, 15),
            status=FieldCrop.Status.ACTIVE,
        )

        self.operation = Operation.objects.create(
            field_crop=self.field_crop,
            type=Operation.Type.WATERING,
            date=date(2026, 3, 20),
            status=Operation.Status.DONE,
            performed_by=self.user,
        )
        self.second_operation = Operation.objects.create(
            field_crop=self.field_crop,
            type=Operation.Type.FERTILIZING,
            date=date(2026, 3, 25),
            status=Operation.Status.DONE,
            performed_by=self.user,
        )
        self.other_user_operation = Operation.objects.create(
            field_crop=self.other_field_crop,
            type=Operation.Type.PLANTING,
            date=date(2026, 3, 22),
            status=Operation.Status.DONE,
            performed_by=self.second_user,
        )

        self.water = Resource.objects.create(
            name="Water",
            unit="l",
            type="water",
            cost_per_unit=Decimal("2.50"),
        )
        self.fertilizer = Resource.objects.create(
            name="Nitrogen",
            unit="kg",
            type="fertilizer",
            cost_per_unit=Decimal("10.00"),
        )
        self.seed = Resource.objects.create(
            name="Seed pack",
            unit="kg",
            type="seed",
            cost_per_unit=Decimal("3.00"),
        )

        OperationResource.objects.create(
            operation=self.operation,
            resource=self.water,
            quantity=Decimal("4.00"),
        )
        OperationResource.objects.create(
            operation=self.operation,
            resource=self.fertilizer,
            quantity=Decimal("2.00"),
        )
        OperationResource.objects.create(
            operation=self.second_operation,
            resource=self.water,
            quantity=Decimal("1.50"),
        )
        OperationResource.objects.create(
            operation=self.other_user_operation,
            resource=self.seed,
            quantity=Decimal("7.00"),
        )

    def test_calculate_operation_cost(self):
        self.assertEqual(calculate_operation_cost(self.operation), Decimal("30.00"))
        self.assertEqual(self.operation.get_total_cost(), Decimal("30.00"))

    def test_get_operation_resources_summary(self):
        self.assertEqual(
            get_operation_resources_summary(self.operation),
            {
                "water": Decimal("4.00"),
                "fertilizer": Decimal("2.00"),
            },
        )

    def test_calculate_field_crop_total_cost(self):
        self.assertEqual(calculate_field_crop_total_cost(self.field_crop), Decimal("33.75"))

    def test_get_field_crop_resources(self):
        self.assertEqual(
            get_field_crop_resources(self.field_crop),
            {
                "water": Decimal("5.50"),
                "fertilizer": Decimal("2.00"),
            },
        )

    def test_calculate_cost_per_hectare(self):
        self.assertEqual(calculate_cost_per_hectare(self.field_crop), Decimal("3.375"))

    def test_calculate_cost_per_hectare_for_zero_area(self):
        self.field.area = Decimal("0")
        self.field.save(update_fields=["area"])
        self.field_crop.refresh_from_db()

        self.assertEqual(calculate_cost_per_hectare(self.field_crop), Decimal("0"))

    def test_calculate_user_total_cost(self):
        self.assertEqual(calculate_user_total_cost(self.user), Decimal("33.75"))

    def test_calculate_season_total_cost(self):
        self.assertEqual(calculate_season_total_cost(self.season, self.user), Decimal("33.75"))
