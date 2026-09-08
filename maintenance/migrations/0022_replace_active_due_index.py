from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("maintenance", "0021_performance_indexes"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="workorder",
            name="wo_active_due_idx",
        ),
        migrations.AddIndex(
            model_name="workorder",
            index=models.Index(
                fields=["company", "due_date", "-created_at"],
                name="wo_active_due_idx",
            ),
        ),
    ]
