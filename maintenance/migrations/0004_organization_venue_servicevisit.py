"""
Replace Location with Organization → Venue hierarchy.
Add ServiceVisit model and service_visit FK on WorkOrder.
Replace Piano.location + location_in_venue with venue + section/room fields.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_locations_to_venues(apps, schema_editor):
    """
    For every existing Location, create:
      - one Organization (named after the Location)
      - one Venue under that Organization (copying the Location data)
    Then re-point every Piano from location_id → venue_id.
    """
    Location = apps.get_model('maintenance', 'Location')
    Organization = apps.get_model('maintenance', 'Organization')
    Piano = apps.get_model('maintenance', 'Piano')
    Venue = apps.get_model('maintenance', 'Venue')

    # If there are no locations, create a default org so venue FK can be populated
    locations = list(Location.objects.all())

    if not locations:
        # No data to migrate — but we still need at least one org+venue
        # if pianos exist (shouldn't, but be safe)
        if Piano.objects.exists():
            org = Organization.objects.create(name="Default Organization")
            venue = Venue.objects.create(name="Default Venue", organization=org)
            Piano.objects.filter(venue__isnull=True).update(venue=venue)
        return

    for loc in locations:
        # Create org per location (can be consolidated later by the user)
        org = Organization.objects.create(
            name=loc.name,
            address=loc.address,
        )
        venue = Venue.objects.create(
            name=loc.name,
            organization=org,
            address=loc.address,
        )
        # Point pianos that were at this location to the new venue
        Piano.objects.filter(location_id=loc.pk).update(venue=venue)


def reverse_venues_to_locations(apps, schema_editor):
    """Reverse: create Locations from Venues, re-point pianos."""
    Location = apps.get_model('maintenance', 'Location')
    Venue = apps.get_model('maintenance', 'Venue')
    Piano = apps.get_model('maintenance', 'Piano')

    for venue in Venue.objects.all():
        loc = Location.objects.create(
            name=venue.name,
            address=venue.address,
        )
        Piano.objects.filter(venue_id=venue.pk).update(location=loc)


class Migration(migrations.Migration):

    dependencies = [
        ('maintenance', '0003_workorder_task_type'),
    ]

    operations = [
        # 1. Create Organization
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('short_name', models.CharField(blank=True, max_length=50)),
                ('address', models.TextField(blank=True)),
                ('contact_name', models.CharField(blank=True, max_length=200)),
                ('contact_email', models.EmailField(blank=True, max_length=254)),
                ('contact_phone', models.CharField(blank=True, max_length=50)),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        # 2. Create Venue
        migrations.CreateModel(
            name='Venue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('short_name', models.CharField(blank=True, max_length=50)),
                ('address', models.TextField(blank=True)),
                ('on_site_contact', models.TextField(blank=True, help_text='Local contact at this venue — name, role, phone.')),
                ('parking_notes', models.TextField(blank=True)),
                ('access_notes', models.TextField(blank=True, help_text='General access instructions for the building.')),
                ('notes', models.TextField(blank=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='venues', to='maintenance.organization')),
            ],
            options={
                'ordering': ['organization', 'name'],
            },
        ),
        # 3. Create ServiceVisit
        migrations.CreateModel(
            name='ServiceVisit',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('time_in', models.TimeField(blank=True, null=True)),
                ('time_out', models.TimeField(blank=True, null=True)),
                ('miles_driven', models.DecimalField(blank=True, decimal_places=1, max_digits=6, null=True)),
                ('status', models.CharField(choices=[('Planned', 'Planned'), ('In Progress', 'In Progress'), ('Complete', 'Complete')], default='Planned', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('technician', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='service_visits', to=settings.AUTH_USER_MODEL)),
                ('venue', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='service_visits', to='maintenance.venue')),
            ],
            options={
                'ordering': ['-date', '-created_at'],
            },
        ),
        # 4. Add service_visit FK to WorkOrder (nullable)
        migrations.AddField(
            model_name='workorder',
            name='service_visit',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='work_orders', to='maintenance.servicevisit'),
        ),
        # 5. Add venue FK to Piano (nullable initially for data migration)
        migrations.AddField(
            model_name='piano',
            name='venue',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name='pianos', to='maintenance.venue'),
            preserve_default=False,
        ),
        # 6. Add new piano location fields
        migrations.AddField(
            model_name='piano',
            name='section',
            field=models.CharField(blank=True, help_text='Optional grouping within venue (building, floor, wing).', max_length=200),
        ),
        migrations.AddField(
            model_name='piano',
            name='room',
            field=models.CharField(blank=True, help_text='Specific spot — room name or number.', max_length=200),
        ),
        migrations.AddField(
            model_name='piano',
            name='room_description',
            field=models.TextField(blank=True, help_text='Directions to help a first-time visitor find this room.'),
        ),
        migrations.AddField(
            model_name='piano',
            name='room_access_notes',
            field=models.TextField(blank=True, help_text='Key codes, access hours, or other entry instructions.'),
        ),
        # 7. Data migration: Location → Organization + Venue, re-point Piano FKs
        migrations.RunPython(migrate_locations_to_venues, reverse_venues_to_locations),
        # 8. Now make venue non-nullable
        migrations.AlterField(
            model_name='piano',
            name='venue',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pianos', to='maintenance.venue'),
        ),
        # 9. Remove old fields
        migrations.RemoveField(
            model_name='piano',
            name='location',
        ),
        migrations.RemoveField(
            model_name='piano',
            name='location_in_venue',
        ),
        # 10. Update Meta ordering
        migrations.AlterModelOptions(
            name='piano',
            options={'ordering': ['venue', 'name']},
        ),
        # 11. Delete old Location model
        migrations.DeleteModel(
            name='Location',
        ),
    ]
