from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_alter_fieldcrop_status_alter_resource_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="agronomistassignment",
            name="can_manage_field_crops",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="agronomistassignment",
            name="can_manage_operations",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="agronomistassignment",
            name="can_manage_seasons",
            field=models.BooleanField(default=False),
        ),
    ]
