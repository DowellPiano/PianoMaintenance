from django.db import migrations, models
from django.core.validators import MinValueValidator


class Migration(migrations.Migration):

    dependencies = [
        ("maintenance", "0022_replace_active_due_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="piano",
            name="warning_days_before",
            field=models.IntegerField(
                default=7,
                help_text="Create preventive work orders this many days before they are due.",
                validators=[MinValueValidator(0)],
            ),
        ),
    ]
