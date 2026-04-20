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
from core.services.reporting.dashboard import get_dashboard_data
from core.services.reporting.reports import get_field_crop_report, get_season_report


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

        self.spring_season = Season.objects.create(
            name="Spring",
            year=2026,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 5, 31),
        )
        self.summer_season = Season.objects.create(
            name="Summer",
            year=2026,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 8, 31),
        )

        self.crop = Crop.objects.create(
            name="Wheat",
            description="Main crop",
            category="Grain",
        )

        self.field = Field.objects.create(
            name="North field",
            area=Decimal("10.00"),
            location="Sector A",
            soil_type="Loam",
            owner=self.user,
        )
        self.zero_area_field = Field.objects.create(
            name="Zero area field",
            area=Decimal("0"),
            location="Sector Z",
            soil_type="Clay",
            owner=self.user,
        )
        self.second_user_field = Field.objects.create(
            name="South field",
            area=Decimal("5.00"),
            location="Sector B",
            soil_type="Sandy",
            owner=self.second_user,
        )

        self.spring_field_crop = FieldCrop.objects.create(
            field=self.field,
            crop=self.crop,
            season=self.spring_season,
            planting_date=date(2026, 3, 10),
            status=FieldCrop.Status.ACTIVE,
        )
        self.summer_field_crop = FieldCrop.objects.create(
            field=self.field,
            crop=self.crop,
            season=self.summer_season,
            planting_date=date(2026, 6, 10),
            status=FieldCrop.Status.ACTIVE,
        )
        self.empty_field_crop = FieldCrop.objects.create(
            field=self.zero_area_field,
            crop=self.crop,
            season=self.spring_season,
            planting_date=date(2026, 3, 12),
            status=FieldCrop.Status.PLANNED,
        )
        self.second_user_field_crop = FieldCrop.objects.create(
            field=self.second_user_field,
            crop=self.crop,
            season=self.spring_season,
            planting_date=date(2026, 3, 15),
            status=FieldCrop.Status.ACTIVE,
        )

        self.water = Resource.objects.create(
            name="Water",
            unit="l",
            type=Resource.Type.WATER,
            cost_per_unit=Decimal("2.50"),
        )
        self.irrigation_water = Resource.objects.create(
            name="Irrigation water",
            unit="l",
            type=Resource.Type.WATER,
            cost_per_unit=Decimal("2.00"),
        )
        self.fertilizer = Resource.objects.create(
            name="Nitrogen",
            unit="kg",
            type=Resource.Type.FERTILIZER,
            cost_per_unit=Decimal("10.00"),
        )
        self.seed = Resource.objects.create(
            name="Seed pack",
            unit="kg",
            type=Resource.Type.SEED,
            cost_per_unit=Decimal("3.00"),
        )

        self.operation_without_resources = Operation.objects.create(
            field_crop=self.spring_field_crop,
            type=Operation.Type.PLANTING,
            date=date(2026, 3, 18),
            status=Operation.Status.PLANNED,
            performed_by=self.user,
        )
        self.spring_operation_1 = Operation.objects.create(
            field_crop=self.spring_field_crop,
            type=Operation.Type.WATERING,
            date=date(2026, 3, 20),
            status=Operation.Status.DONE,
            performed_by=self.user,
        )
        self.spring_operation_2 = Operation.objects.create(
            field_crop=self.spring_field_crop,
            type=Operation.Type.FERTILIZING,
            date=date(2026, 3, 25),
            status=Operation.Status.DONE,
            performed_by=self.user,
        )
        self.summer_operation = Operation.objects.create(
            field_crop=self.summer_field_crop,
            type=Operation.Type.HARVESTING,
            date=date(2026, 7, 1),
            status=Operation.Status.DONE,
            performed_by=self.user,
        )
        self.second_user_operation = Operation.objects.create(
            field_crop=self.second_user_field_crop,
            type=Operation.Type.PLANTING,
            date=date(2026, 3, 22),
            status=Operation.Status.DONE,
            performed_by=self.second_user,
        )

        OperationResource.objects.create(
            operation=self.spring_operation_1,
            resource=self.water,
            quantity=Decimal("4.00"),
        )
        OperationResource.objects.create(
            operation=self.spring_operation_1,
            resource=self.irrigation_water,
            quantity=Decimal("1.50"),
        )
        OperationResource.objects.create(
            operation=self.spring_operation_1,
            resource=self.fertilizer,
            quantity=Decimal("2.00"),
        )
        OperationResource.objects.create(
            operation=self.spring_operation_2,
            resource=self.water,
            quantity=Decimal("1.00"),
        )
        OperationResource.objects.create(
            operation=self.summer_operation,
            resource=self.seed,
            quantity=Decimal("2.00"),
        )
        OperationResource.objects.create(
            operation=self.second_user_operation,
            resource=self.seed,
            quantity=Decimal("7.00"),
        )

    def assertIsDecimalAndEqual(self, actual, expected):
        self.assertIsInstance(actual, Decimal)
        self.assertEqual(actual, expected)

    def test_calculate_operation_cost_returns_decimal_and_zero_without_resources(self):
        self.assertIsDecimalAndEqual(
            calculate_operation_cost(self.operation_without_resources),
            Decimal("0"),
        )
        self.assertIsDecimalAndEqual(
            self.operation_without_resources.get_total_cost(),
            Decimal("0"),
        )

    def test_calculate_operation_cost_sums_all_resources(self):
        self.assertIsDecimalAndEqual(
            calculate_operation_cost(self.spring_operation_1),
            Decimal("33.00"),
        )

    def test_get_operation_resources_summary_sums_resources_with_same_type(self):
        summary = get_operation_resources_summary(self.spring_operation_1)

        self.assertEqual(
            summary,
            {
                Resource.Type.WATER: Decimal("5.50"),
                Resource.Type.FERTILIZER: Decimal("2.00"),
            },
        )

    def test_calculate_field_crop_total_cost_returns_decimal_and_zero_without_operations(self):
        self.assertIsDecimalAndEqual(
            calculate_field_crop_total_cost(self.empty_field_crop),
            Decimal("0"),
        )

    def test_calculate_field_crop_total_cost_sums_multiple_operations(self):
        self.assertIsDecimalAndEqual(
            calculate_field_crop_total_cost(self.spring_field_crop),
            Decimal("35.50"),
        )

    def test_get_field_crop_resources_aggregates_across_operations(self):
        summary = get_field_crop_resources(self.spring_field_crop)

        self.assertEqual(
            summary,
            {
    Resource.Type.WATER: Decimal("6.50"),
    Resource.Type.FERTILIZER: Decimal("2.00"),
},
        )

    def test_calculate_cost_per_hectare_returns_decimal(self):
        self.assertIsDecimalAndEqual(
            calculate_cost_per_hectare(self.spring_field_crop),
            Decimal("3.55"),
        )

    def test_calculate_cost_per_hectare_returns_zero_for_zero_area(self):
        self.assertIsDecimalAndEqual(
            calculate_cost_per_hectare(self.empty_field_crop),
            Decimal("0"),
        )

    def test_calculate_user_total_cost_filters_other_users_and_returns_decimal(self):
        self.assertIsDecimalAndEqual(
            calculate_user_total_cost(self.user),
            Decimal("41.50"),
        )

    def test_calculate_user_total_cost_does_not_mix_users(self):
        self.assertIsDecimalAndEqual(
            calculate_user_total_cost(self.second_user),
            Decimal("21.00"),
        )

    def test_calculate_season_total_cost_filters_by_season_and_user(self):
        self.assertIsDecimalAndEqual(
            calculate_season_total_cost(self.spring_season, self.user),
            Decimal("35.50"),
        )
        self.assertIsDecimalAndEqual(
            calculate_season_total_cost(self.summer_season, self.user),
            Decimal("6.00"),
        )

    def test_calculate_season_total_cost_does_not_include_other_users(self):
        self.assertIsDecimalAndEqual(
            calculate_season_total_cost(self.spring_season, self.second_user),
            Decimal("21.00"),
        )
    def test_calculate_user_total_cost_empty_user(self):
        empty_user = User.objects.create_user(
            username="empty_user",
            password="testpass123",
            email="empty@example.com",
        )

        self.assertIsDecimalAndEqual(
            calculate_user_total_cost(empty_user),
            Decimal("0"),
        )
    
    def test_decimal_precision(self):
        resource = Resource.objects.create(
            name="Test resource",
            unit="kg",
            type=Resource.Type.FERTILIZER,
            cost_per_unit=Decimal("2.777"),
        )

        operation = Operation.objects.create(
            field_crop=self.spring_field_crop,
            type=Operation.Type.FERTILIZING,
            date=date(2026, 4, 1),
            status=Operation.Status.DONE,
            performed_by=self.user,
        )

        OperationResource.objects.create(
            operation=operation,
            resource=resource,
            quantity=Decimal("1.333"),
        )

        result = calculate_operation_cost(operation)

        self.assertIsInstance(result, Decimal)

    def test_get_dashboard_data_returns_expected_dict(self):
        self.assertEqual(
            get_dashboard_data(self.user),
            {
                "total_cost": Decimal("41.50"),
                "fields_count": 2,
                "operations_count": 4,
                "resources": {
                    Resource.Type.WATER: Decimal("6.50"),
                    Resource.Type.FERTILIZER: Decimal("2.00"),
                    Resource.Type.SEED: Decimal("2.00"),
                },
            },
        )

    def test_get_field_crop_report_returns_expected_dict(self):
        self.assertEqual(
            get_field_crop_report(self.spring_field_crop),
            {
                "field_crop_id": self.spring_field_crop.id,
                "field": {
                    "id": self.spring_field_crop.field.id,
                    "name": self.spring_field_crop.field.name,
                },
                "crop": {
                    "id": self.spring_field_crop.crop.id,
                    "name": self.spring_field_crop.crop.name,
                },
                "season": {
                    "id": self.spring_field_crop.season.id,
                    "name": self.spring_field_crop.season.name,
                    "year": self.spring_field_crop.season.year,
                },
                "status": self.spring_field_crop.status,
                "operations_count": 3,
                "total_cost": Decimal("35.50"),
                "cost_per_hectare": Decimal("3.55"),
                "resources": {
                    Resource.Type.WATER: Decimal("6.50"),
                    Resource.Type.FERTILIZER: Decimal("2.00"),
                },
            },
        )

    def test_get_season_report_returns_expected_dict(self):
        self.assertEqual(
            get_season_report(self.spring_season, self.user),
            {
                "season_id": self.spring_season.id,
                "season": {
                    "id": self.spring_season.id,
                    "name": self.spring_season.name,
                    "year": self.spring_season.year,
                },
                "total_cost": Decimal("35.50"),
                "fields_count": 2,
                "operations_count": 3,
                "resources": {
                    Resource.Type.WATER: Decimal("6.50"),
                    Resource.Type.FERTILIZER: Decimal("2.00"),
                },
            },
        )
