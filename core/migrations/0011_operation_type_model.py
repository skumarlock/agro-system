from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


DEFAULT_OPERATION_TYPES = [
    "\u043f\u043e\u043b\u0438\u0432",
    "\u043f\u043e\u0441\u0430\u0434\u043a\u0430",
    "\u0443\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u0435",
    "\u0441\u0431\u043e\u0440 \u0443\u0440\u043e\u0436\u0430\u044f",
]

TYPE_MAP = {
    "watering": "\u043f\u043e\u043b\u0438\u0432",
    "planting": "\u043f\u043e\u0441\u0430\u0434\u043a\u0430",
    "fertilizing": "\u0443\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u0435",
    "harvesting": "\u0441\u0431\u043e\u0440 \u0443\u0440\u043e\u0436\u0430\u044f",
    "\u043f\u043e\u043b\u0438\u0432": "\u043f\u043e\u043b\u0438\u0432",
    "\u043f\u043e\u0441\u0430\u0434\u043a\u0430": "\u043f\u043e\u0441\u0430\u0434\u043a\u0430",
    "\u0443\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u0435": "\u0443\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u0435",
    "\u0441\u0431\u043e\u0440 \u0443\u0440\u043e\u0436\u0430\u044f": "\u0441\u0431\u043e\u0440 \u0443\u0440\u043e\u0436\u0430\u044f",
}


def migrate_operation_types(apps, schema_editor):
    Operation = apps.get_model("core", "Operation")
    OperationType = apps.get_model("core", "OperationType")

    defaults = {
        name: OperationType.objects.get_or_create(owner=None, name=name)[0]
        for name in DEFAULT_OPERATION_TYPES
    }
    fallback = defaults[DEFAULT_OPERATION_TYPES[0]]

    for operation in Operation.objects.all().iterator():
        old_type = operation.type or ""
        type_name = TYPE_MAP.get(old_type, old_type.strip() or fallback.name)
        op_type = defaults.get(type_name)
        if op_type is None:
            op_type, _ = OperationType.objects.get_or_create(owner=None, name=type_name)
        operation.type_new_id = op_type.id
        operation.save(update_fields=["type_new"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_season_unique_owner_dates"),
    ]

    operations = [
        migrations.CreateModel(
            name="OperationType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100)),
                ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="operation_types", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("owner", "name")},
            },
        ),
        migrations.AddField(
            model_name="operation",
            name="type_new",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="operations", to="core.operationtype"),
        ),
        migrations.RunPython(migrate_operation_types, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="operation",
            name="type",
        ),
        migrations.RenameField(
            model_name="operation",
            old_name="type_new",
            new_name="type",
        ),
        migrations.AlterField(
            model_name="operation",
            name="type",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="operations", to="core.operationtype"),
        ),
        migrations.AddIndex(
            model_name="season",
            index=models.Index(fields=["owner", "year"], name="core_season_owner_year_idx"),
        ),
    ]
