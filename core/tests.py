from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from core.forms import OperationForm
from core.models import (
    AgronomistAssignment,
    Crop,
    Field,
    FieldCrop,
    Operation,
    OperationResource,
    OperationType,
    Resource,
    Season,
    User,
)
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
            price_per_unit=resource.cost_per_unit,
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


class ReportingAPITests(BusinessLogicServicesTests):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_dashboard_endpoint_returns_service_data(self):
        response = self.client.get(reverse("api-dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "total_cost": 41.5,
                "fields_count": 2,
                "operations_count": 4,
                "resources": {
                    "water": 6.5,
                    "fertilizer": 2.0,
                    "seed": 2.0,
                },
            },
        )

    def test_field_crops_endpoint_returns_reports_for_authenticated_user(self):
        response = self.client.get(reverse("api-field-crops"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
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
                    "total_cost": 35.5,
                    "cost_per_hectare": 3.55,
                    "resources": {
                        "water": 6.5,
                        "fertilizer": 2.0,
                    },
                },
                {
                    "field_crop_id": self.summer_field_crop.id,
                    "field": {
                        "id": self.summer_field_crop.field.id,
                        "name": self.summer_field_crop.field.name,
                    },
                    "crop": {
                        "id": self.summer_field_crop.crop.id,
                        "name": self.summer_field_crop.crop.name,
                    },
                    "season": {
                        "id": self.summer_field_crop.season.id,
                        "name": self.summer_field_crop.season.name,
                        "year": self.summer_field_crop.season.year,
                    },
                    "status": self.summer_field_crop.status,
                    "operations_count": 1,
                    "total_cost": 6.0,
                    "cost_per_hectare": 0.6,
                    "resources": {
                        "seed": 2.0,
                    },
                },
                {
                    "field_crop_id": self.empty_field_crop.id,
                    "field": {
                        "id": self.empty_field_crop.field.id,
                        "name": self.empty_field_crop.field.name,
                    },
                    "crop": {
                        "id": self.empty_field_crop.crop.id,
                        "name": self.empty_field_crop.crop.name,
                    },
                    "season": {
                        "id": self.empty_field_crop.season.id,
                        "name": self.empty_field_crop.season.name,
                        "year": self.empty_field_crop.season.year,
                    },
                    "status": self.empty_field_crop.status,
                    "operations_count": 0,
                    "total_cost": 0.0,
                    "cost_per_hectare": 0.0,
                    "resources": {},
                },
            ],
        )

    def test_season_report_endpoint_returns_requested_season_for_authenticated_user(self):
        response = self.client.get(reverse("api-season-report", args=[self.spring_season.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "season_id": self.spring_season.id,
                "season": {
                    "id": self.spring_season.id,
                    "name": self.spring_season.name,
                    "year": self.spring_season.year,
                },
                "total_cost": 35.5,
                "fields_count": 2,
                "operations_count": 3,
                "resources": {
                    "water": 6.5,
                    "fertilizer": 2.0,
                },
            },
        )

    def test_endpoints_require_authentication(self):
        self.client.force_authenticate(user=None)

        dashboard_response = self.client.get(reverse("api-dashboard"))
        field_crops_response = self.client.get(reverse("api-field-crops"))
        season_response = self.client.get(reverse("api-season-report", args=[self.spring_season.id]))

        self.assertEqual(dashboard_response.status_code, 403)
        self.assertEqual(field_crops_response.status_code, 403)
        self.assertEqual(season_response.status_code, 403)


class YearBasedOperationFlowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner",
            password="testpass123",
            email="owner@example.com",
        )
        self.owner_two = User.objects.create_user(
            username="owner_two",
            password="testpass123",
            email="owner-two@example.com",
        )
        self.agronomist = User.objects.create_user(
            username="agro",
            password="testpass123",
            email="agro@example.com",
            role=User.Role.AGRONOMIST,
        )
        self.worker = User.objects.create_user(
            username="worker",
            password="testpass123",
            email="worker@example.com",
            role=User.Role.WORKER,
            owner=self.owner,
        )
        self.other_worker = User.objects.create_user(
            username="worker_two",
            password="testpass123",
            email="worker-two@example.com",
            role=User.Role.WORKER,
            owner=self.owner_two,
        )

        AgronomistAssignment.objects.create(owner=self.owner, agronomist=self.agronomist)
        AgronomistAssignment.objects.create(owner=self.owner_two, agronomist=self.agronomist)

        self.field = Field.objects.create(
            name="North field",
            area=Decimal("12.00"),
            location="Sector A",
            soil_type="Loam",
            owner=self.owner,
        )
        self.other_field = Field.objects.create(
            name="South field",
            area=Decimal("9.00"),
            location="Sector B",
            soil_type="Clay",
            owner=self.owner_two,
        )
        self.crop = Crop.objects.create(name="Wheat")
        self.other_crop = Crop.objects.create(name="Corn")

        self.spring_2026 = Season.objects.create(
            name="Spring",
            year=2026,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 5, 31),
            owner=self.owner,
        )
        self.summer_2026 = Season.objects.create(
            name="Summer",
            year=2026,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 8, 31),
            owner=self.owner,
        )
        self.spring_2027 = Season.objects.create(
            name="Spring",
            year=2027,
            start_date=date(2027, 3, 1),
            end_date=date(2027, 5, 31),
            owner=self.owner,
        )
        self.owner_two_spring_2026 = Season.objects.create(
            name="Spring",
            year=2026,
            start_date=date(2026, 3, 5),
            end_date=date(2026, 5, 25),
            owner=self.owner_two,
        )

        self.spring_fc = FieldCrop.objects.create(
            field=self.field,
            crop=self.crop,
            season=self.spring_2026,
            planting_date=date(2026, 3, 10),
            status=FieldCrop.Status.PLANNED,
        )
        self.summer_fc = FieldCrop.objects.create(
            field=self.field,
            crop=self.crop,
            season=self.summer_2026,
            planting_date=date(2026, 6, 10),
            status=FieldCrop.Status.PLANNED,
        )
        self.future_fc = FieldCrop.objects.create(
            field=self.field,
            crop=self.other_crop,
            season=self.spring_2027,
            planting_date=date(2027, 3, 10),
            status=FieldCrop.Status.PLANNED,
        )
        self.other_owner_fc = FieldCrop.objects.create(
            field=self.other_field,
            crop=self.crop,
            season=self.owner_two_spring_2026,
            planting_date=date(2026, 3, 12),
            status=FieldCrop.Status.PLANNED,
        )

        self.public_type = OperationType.objects.create(owner=None, name="Irrigation")
        self.owner_type = OperationType.objects.create(owner=self.owner, name="Spraying")

        self.resource = Resource.objects.create(
            name="Water",
            unit="l",
            type=Resource.Type.WATER,
            cost_per_unit=Decimal("1.50"),
        )

        self.spring_done = Operation.objects.create(
            field_crop=self.spring_fc,
            type=self.public_type,
            date=date(2026, 4, 10),
            status=Operation.Status.DONE,
            performed_by=self.worker,
        )
        self.summer_planned = Operation.objects.create(
            field_crop=self.summer_fc,
            type=self.public_type,
            date=date(2026, 7, 10),
            status=Operation.Status.PLANNED,
            performed_by=self.worker,
        )
        self.other_year_op = Operation.objects.create(
            field_crop=self.future_fc,
            type=self.public_type,
            date=date(2027, 4, 12),
            status=Operation.Status.PLANNED,
            performed_by=self.worker,
        )
        self.other_owner_op = Operation.objects.create(
            field_crop=self.other_owner_fc,
            type=self.public_type,
            date=date(2026, 4, 11),
            status=Operation.Status.DONE,
            performed_by=self.other_worker,
        )

        OperationResource.objects.create(
            operation=self.spring_done,
            resource=self.resource,
            quantity=Decimal("2.00"),
        )

    @patch("django.utils.timezone.now", return_value=datetime(2026, 6, 15, tzinfo=timezone.utc))
    def test_same_crop_across_spring_and_summer_is_active_for_both_field_crops(self, _mock_now):
        self.assertEqual(self.spring_fc.get_computed_status(), FieldCrop.Status.ACTIVE)
        self.assertEqual(self.summer_fc.get_computed_status(), FieldCrop.Status.ACTIVE)

    @patch("django.utils.timezone.now", return_value=datetime(2027, 2, 1, tzinfo=timezone.utc))
    def test_future_operations_are_planned(self, _mock_now):
        self.assertEqual(self.future_fc.get_computed_status(), FieldCrop.Status.PLANNED)

    @patch("django.utils.timezone.now", return_value=datetime(2026, 8, 1, tzinfo=timezone.utc))
    def test_past_done_operations_are_harvested(self, _mock_now):
        harvested_fc = FieldCrop.objects.create(
            field=self.field,
            crop=Crop.objects.create(name="Barley"),
            season=self.spring_2026,
            planting_date=date(2026, 3, 15),
            harvest_date=date(2026, 7, 20),
            status=FieldCrop.Status.PLANNED,
        )
        Operation.objects.create(
            field_crop=harvested_fc,
            type=self.owner_type,
            date=date(2026, 4, 1),
            status=Operation.Status.DONE,
            performed_by=self.worker,
        )
        Operation.objects.create(
            field_crop=harvested_fc,
            type=self.owner_type,
            date=date(2026, 6, 1),
            status=Operation.Status.DONE,
            performed_by=self.worker,
        )

        self.assertEqual(harvested_fc.get_computed_status(), FieldCrop.Status.HARVESTED)

    def test_operation_form_no_longer_exposes_field_crop(self):
        self.assertNotIn("field_crop", OperationForm.base_fields)

    def test_create_operation_page_uses_year_and_season_labels_without_field_crop_widget(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("create-operation"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Год")
        self.assertContains(response, "Сезон")
        self.assertNotContains(response, 'name="field_crop"', html=False)
        self.assertNotContains(response, 'id="id_field_crop"', html=False)

    def test_create_operation_post_resolves_field_crop_from_cascade_fields(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("create-operation"),
            {
                "field": str(self.field.id),
                "season": str(self.spring_2026.id),
                "crop": str(self.crop.id),
                "type": str(self.owner_type.id),
                "date": "2026-04-20",
                "status": Operation.Status.PLANNED,
                "performed_by": str(self.worker.id),
                "description": "Follow-up operation",
                "resource": [str(self.resource.id)],
                "quantity": ["3.5"],
            },
        )

        self.assertEqual(response.status_code, 302)
        created = Operation.objects.exclude(pk__in=[
            self.spring_done.pk,
            self.summer_planned.pk,
            self.other_year_op.pk,
            self.other_owner_op.pk,
        ]).get()
        self.assertEqual(created.field_crop, self.spring_fc)
        self.assertEqual(created.type, self.owner_type)
        self.assertEqual(created.performed_by, self.worker)

    def test_create_operation_invalid_combination_returns_visible_error(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("create-operation"),
            {
                "field": str(self.field.id),
                "season": str(self.spring_2026.id),
                "crop": str(self.other_crop.id),
                "type": str(self.owner_type.id),
                "date": "2026-04-20",
                "status": Operation.Status.PLANNED,
                "performed_by": str(self.worker.id),
                "description": "Invalid combo",
                "resource": [str(self.resource.id)],
                "quantity": ["1.0"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid field/crop/season combination")
        self.assertFalse(Operation.objects.filter(description="Invalid combo").exists())

    def test_create_operation_falls_back_to_same_year_field_crop_when_season_differs(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("create-operation"),
            {
                "field": str(self.field.id),
                "season": str(self.summer_2026.id),
                "crop": str(self.crop.id),
                "type": str(self.owner_type.id),
                "date": "2026-08-31",
                "status": Operation.Status.DONE,
                "performed_by": str(self.worker.id),
                "description": "Year fallback harvest",
                "resource": [str(self.resource.id)],
                "quantity": ["1.0"],
            },
        )

        self.assertEqual(response.status_code, 302)
        created = Operation.objects.get(description="Year fallback harvest")
        self.assertEqual(created.field_crop.season.year, 2026)
        self.assertEqual(created.field_crop.crop, self.crop)

    @patch("django.utils.timezone.now", return_value=datetime(2026, 9, 2, tzinfo=timezone.utc))
    def test_done_harvest_operation_updates_harvest_date_and_marks_field_crop_harvested(self, _mock_now):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("create-operation"),
            {
                "field": str(self.field.id),
                "season": str(self.summer_2026.id),
                "crop": str(self.crop.id),
                "type": str(self.public_type.id),
                "new_operation_type": "Сбор урожая",
                "date": "2026-08-31",
                "status": Operation.Status.DONE,
                "performed_by": str(self.worker.id),
                "description": "Harvest done",
                "resource": [str(self.resource.id)],
                "quantity": ["2.0"],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.summer_fc.refresh_from_db()
        self.assertEqual(self.summer_fc.harvest_date, date(2026, 8, 31))
        self.assertEqual(self.summer_fc.get_computed_status(), FieldCrop.Status.HARVESTED)

    @patch("django.utils.timezone.now", return_value=datetime(2026, 9, 2, tzinfo=timezone.utc))
    def test_field_crop_list_renders_harvested_badge_for_computed_status(self, _mock_now):
        self.summer_fc.harvest_date = date(2026, 8, 31)
        self.summer_fc.save(update_fields=["harvest_date", "updated_at"])
        self.client.force_login(self.owner)

        response = self.client.get(reverse("field-crops"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Собрано")

    @patch("django.utils.timezone.now", return_value=datetime(2026, 4, 27, tzinfo=timezone.utc))
    def test_field_detail_renders_active_badge_for_current_year(self, _mock_now):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("field-detail", args=[self.field.id]),
            {"season": self.spring_2026.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Активно")

    def test_field_detail_uses_year_scoped_operations_and_excludes_other_years(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("field-detail", args=[self.field.id]),
            {"season": self.spring_2026.id},
        )

        self.assertEqual(response.status_code, 200)
        operations = list(response.context["operations"])
        operation_ids = {op.id for op in operations}
        self.assertIn(self.spring_done.id, operation_ids)
        self.assertIn(self.summer_planned.id, operation_ids)
        self.assertNotIn(self.other_year_op.id, operation_ids)

    def test_seasons_api_returns_active_owner_data_for_agronomist_context(self):
        self.client.force_login(self.agronomist)
        session = self.client.session
        session["active_owner_id"] = self.owner.id
        session.save()

        response = self.client.get(
            reverse("api-seasons-by-year"),
            {"year": 2026, "owner_id": self.owner.id},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("seasons", payload)
        self.assertGreaterEqual(len(payload["seasons"]), 1)
        for item in payload["seasons"]:
            self.assertEqual(
                set(["id", "name", "start_date", "end_date", "owner_id"]).issubset(item.keys()),
                True,
            )
            self.assertEqual(item["owner_id"], self.owner.id)

    def test_agronomist_create_operation_flow_is_limited_to_active_owner(self):
        link = AgronomistAssignment.objects.get(owner=self.owner, agronomist=self.agronomist)
        link.can_manage_operations = True
        link.save(update_fields=["can_manage_operations"])
        self.client.force_login(self.agronomist)
        session = self.client.session
        session["active_owner_id"] = self.owner.id
        session.save()

        response = self.client.get(reverse("create-operation"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["owner_id"] for item in response.context["fields"]}, {self.owner.id})

        post_response = self.client.post(
            reverse("create-operation"),
            {
                "field": str(self.other_field.id),
                "season": str(self.owner_two_spring_2026.id),
                "crop": str(self.crop.id),
                "type": str(self.public_type.id),
                "date": "2026-04-21",
                "status": Operation.Status.PLANNED,
                "performed_by": str(self.worker.id),
                "description": "Should be rejected",
                "resource": [str(self.resource.id)],
                "quantity": ["1.0"],
            },
        )

        self.assertEqual(post_response.status_code, 200)
        self.assertFalse(
            Operation.objects.filter(
                description="Should be rejected",
                field_crop=self.other_owner_fc,
            ).exists()
        )

    def test_owner_can_create_field_crop_for_own_field(self):
        self.client.force_login(self.owner)
        new_crop = Crop.objects.create(name="Sunflower")

        response = self.client.post(
            reverse("create-field-crop"),
            {
                "field": str(self.field.id),
                "season": str(self.spring_2027.id),
                "crop": str(new_crop.id),
                "planting_date": "2027-03-20",
                "harvest_date": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        created = FieldCrop.objects.get(field=self.field, season=self.spring_2027, crop=new_crop)
        self.assertEqual(created.planting_date, date(2027, 3, 20))

    def test_owner_cannot_create_duplicate_field_crop(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("create-field-crop"),
            {
                "field": str(self.field.id),
                "season": str(self.spring_2026.id),
                "crop": str(self.crop.id),
                "planting_date": "2026-03-10",
                "harvest_date": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already assigned")

    def test_agronomist_cannot_create_field_crop(self):
        self.client.force_login(self.agronomist)

        response = self.client.get(reverse("create-field-crop"))

        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_field_crop_for_any_field(self):
        admin = User.objects.create_user(
            username="admin_user",
            password="testpass123",
            email="admin@example.com",
            role=User.Role.ADMIN,
        )
        self.client.force_login(admin)
        new_crop = Crop.objects.create(name="Rice")

        response = self.client.post(
            reverse("create-field-crop"),
            {
                "field": str(self.other_field.id),
                "season": str(self.owner_two_spring_2026.id),
                "crop": str(new_crop.id),
                "planting_date": "2026-03-18",
                "harvest_date": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            FieldCrop.objects.filter(
                field=self.other_field,
                season=self.owner_two_spring_2026,
                crop=new_crop,
            ).exists()
        )

    def test_create_field_crop_page_contains_year_selector(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("create-field-crop"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Год")
        self.assertContains(response, 'id="season-year-select"', html=False)

    def test_owner_can_edit_field_crop(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("edit-field-crop", args=[self.future_fc.id]),
            {
                "field": str(self.field.id),
                "season": str(self.summer_2026.id),
                "crop": str(self.other_crop.id),
                "planting_date": "2026-06-15",
                "harvest_date": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.future_fc.refresh_from_db()
        self.assertEqual(self.future_fc.season, self.summer_2026)
        self.assertEqual(self.future_fc.planting_date, date(2026, 6, 15))

    def test_owner_can_delete_field_crop(self):
        self.client.force_login(self.owner)

        response = self.client.post(reverse("delete-field-crop", args=[self.future_fc.id]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(FieldCrop.objects.filter(pk=self.future_fc.id).exists())

    def test_owner_can_edit_season(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("edit-season", args=[self.spring_2027.id]),
            {
                "name": "Early Spring",
                "start_date": "2027-02-20",
                "end_date": "2027-05-31",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.spring_2027.refresh_from_db()
        self.assertEqual(self.spring_2027.name, "Early Spring")
        self.assertEqual(self.spring_2027.year, 2027)

    def test_owner_can_delete_season(self):
        self.client.force_login(self.owner)
        season = Season.objects.create(
            name="Autumn",
            year=2027,
            start_date=date(2027, 9, 1),
            end_date=date(2027, 11, 30),
            owner=self.owner,
        )

        response = self.client.post(reverse("delete-season", args=[season.id]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Season.objects.filter(pk=season.id).exists())

    @patch("core.views_ui.now", return_value=datetime(2026, 4, 27, tzinfo=timezone.utc))
    def test_worker_week_filter_only_shows_current_calendar_week(self, _mock_now):
        self.client.force_login(self.worker)
        current_week_op = Operation.objects.create(
            field_crop=self.spring_fc,
            type=self.public_type,
            date=date(2026, 4, 29),
            status=Operation.Status.PLANNED,
            performed_by=self.worker,
        )
        Operation.objects.create(
            field_crop=self.spring_fc,
            type=self.public_type,
            date=date(2028, 7, 15),
            status=Operation.Status.PLANNED,
            performed_by=self.worker,
        )
        Operation.objects.create(
            field_crop=self.future_fc,
            type=self.public_type,
            date=date(2027, 3, 10),
            status=Operation.Status.PLANNED,
            performed_by=self.worker,
        )
        Operation.objects.create(
            field_crop=self.summer_fc,
            type=self.public_type,
            date=date(2026, 8, 10),
            status=Operation.Status.PLANNED,
            performed_by=self.worker,
        )

        response = self.client.get(reverse("my-operations"), {"filter": "week"})

        self.assertEqual(response.status_code, 200)
        operations = list(response.context["page_obj"].object_list)
        self.assertEqual([op.id for op in operations], [current_week_op.id])

    def test_agronomist_owner_detail_explains_year_filter_context(self):
        self.client.force_login(self.agronomist)

        response = self.client.get(
            reverse("agronomist-owner-detail", args=[self.owner.id]),
            {"year": 2026},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Фильтр по году показывает только те поля")
        self.assertContains(response, "Сейчас выбран 2026 год.")

    def test_owner_can_toggle_extended_agronomist_permissions(self):
        self.client.force_login(self.owner)
        link = AgronomistAssignment.objects.get(owner=self.owner, agronomist=self.agronomist)

        for permission_name, field_name in [
            ("operations", "can_manage_operations"),
            ("seasons", "can_manage_seasons"),
            ("field-crops", "can_manage_field_crops"),
        ]:
            response = self.client.post(reverse("toggle-agronomist-permission", args=[link.id, permission_name]))
            self.assertEqual(response.status_code, 200)
            link.refresh_from_db()
            self.assertTrue(getattr(link, field_name))

    def test_agronomist_without_operation_permission_cannot_edit_operation(self):
        self.client.force_login(self.agronomist)

        response = self.client.get(reverse("edit-operation", args=[self.spring_done.id]))

        self.assertEqual(response.status_code, 403)

    def test_agronomist_with_operation_permission_can_edit_operation(self):
        link = AgronomistAssignment.objects.get(owner=self.owner, agronomist=self.agronomist)
        link.can_manage_operations = True
        link.save(update_fields=["can_manage_operations"])
        self.client.force_login(self.agronomist)

        response = self.client.get(reverse("edit-operation", args=[self.spring_done.id]))

        self.assertEqual(response.status_code, 200)

    def test_agronomist_with_season_permission_can_edit_season(self):
        link = AgronomistAssignment.objects.get(owner=self.owner, agronomist=self.agronomist)
        link.can_manage_seasons = True
        link.save(update_fields=["can_manage_seasons"])
        self.client.force_login(self.agronomist)

        response = self.client.post(
            reverse("edit-season", args=[self.spring_2027.id]),
            {
                "name": "Managed Spring",
                "start_date": "2027-02-20",
                "end_date": "2027-05-31",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.spring_2027.refresh_from_db()
        self.assertEqual(self.spring_2027.name, "Managed Spring")

    def test_agronomist_with_field_crop_permission_can_edit_field_crop(self):
        link = AgronomistAssignment.objects.get(owner=self.owner, agronomist=self.agronomist)
        link.can_manage_field_crops = True
        link.save(update_fields=["can_manage_field_crops"])
        self.client.force_login(self.agronomist)

        response = self.client.post(
            reverse("edit-field-crop", args=[self.future_fc.id]),
            {
                "field": str(self.field.id),
                "season": str(self.summer_2026.id),
                "crop": str(self.other_crop.id),
                "planting_date": "2026-06-20",
                "harvest_date": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.future_fc.refresh_from_db()
        self.assertEqual(self.future_fc.planting_date, date(2026, 6, 20))
