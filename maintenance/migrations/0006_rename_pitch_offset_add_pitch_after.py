from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('maintenance', '0005_conditionreading_recorded_at_editable'),
    ]

    operations = [
        # Rename the Python attribute; db_column='pitch_before_cents' keeps
        # the underlying column name unchanged, so no ALTER TABLE is needed.
        migrations.RenameField(
            model_name='conditionreading',
            old_name='pitch_offset_cents',
            new_name='pitch_before_cents',
        ),
        migrations.AddField(
            model_name='conditionreading',
            name='pitch_after_cents',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=6, null=True
            ),
        ),
    ]
