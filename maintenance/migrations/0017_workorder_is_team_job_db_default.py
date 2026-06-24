from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('maintenance', '0016_workorder_is_team_job'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workorder',
            name='is_team_job',
            field=models.BooleanField(db_default=False, default=False),
        ),
    ]
