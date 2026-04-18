import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('maintenance', '0006_rename_pitch_offset_add_pitch_after'),
    ]

    operations = [
        # Create Team first (no FK to Technician yet — manager added below)
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('manager', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='managed_teams',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        # Add team FK to Technician
        migrations.AddField(
            model_name='technician',
            name='team',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='members',
                to='maintenance.team',
            ),
        ),
    ]
