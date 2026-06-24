from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('maintenance', '0015_alter_companysettings_company_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='workorder',
            name='is_team_job',
            field=models.BooleanField(default=False),
        ),
    ]
