import csv
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import (
    AuditLog,
    Company,
    CompanyMembership,
    ConditionLevel,
    ConditionReading,
    MaintenanceLog,
    Organization,
    Part,
    PartUsed,
    Piano,
    Technician,
    Venue,
    WorkOrder,
)


class CompanyAdminWebTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Company', slug='test-company')
        self.other_company = Company.objects.create(name='Other Company', slug='other-company')
        self.admin = Technician.objects.create_user(
            username='admin',
            password='StrongPass123',
        )
        CompanyMembership.objects.create(
            company=self.company,
            user=self.admin,
            role_admin=True,
            role_technician=True,
        )
        self.client.force_login(self.admin)
        session = self.client.session
        session['active_company_id'] = self.company.pk
        session.save()

    @staticmethod
    def piano_form_data(**overrides):
        data = {
            'name': 'Studio Piano',
            'make': 'Yamaha',
            'model': 'U3',
            'serial_number': '12345',
            'piano_type': Piano.PianoType.UPRIGHT,
            'venue': '',
            'section': '',
            'room': '101',
            'room_description': '',
            'room_access_notes': '',
            'year_built': '2010',
            'year_acquired': '2012',
            'tuning_interval_value': '6',
            'tuning_interval_unit': 'months',
            'regulation_interval_value': '12',
            'regulation_interval_unit': 'months',
            'voicing_interval_value': '12',
            'voicing_interval_unit': 'months',
            'cleaning_interval_value': '6',
            'cleaning_interval_unit': 'months',
            'notes': '',
        }
        data.update(overrides)
        return data

    @staticmethod
    def csv_upload(rows):
        output = StringIO()
        fieldnames = [
            'name', 'make', 'model', 'serial_number', 'piano_type',
            'organization', 'venue', 'section', 'room',
            'year_built', 'year_acquired', 'notes',
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return SimpleUploadedFile(
            'pianos.csv',
            output.getvalue().encode('utf-8'),
            content_type='text/csv',
        )


class CoreCrudFlowTests(CompanyAdminWebTestCase):
    def test_organization_create_and_edit_are_scoped_and_audited(self):
        response = self.client.post(reverse('organization_create'), {
            'name': 'Symphony',
            'short_name': 'SO',
            'address': '1 Music Way',
            'contact_name': 'Pat Manager',
            'contact_email': 'pat@example.com',
            'contact_phone': '555-0100',
            'notes': 'Primary client',
        })

        organization = Organization.objects.get(name='Symphony')
        self.assertRedirects(response, reverse('organization_detail', args=[organization.pk]))
        self.assertEqual(organization.company, self.company)
        self.assertTrue(AuditLog.objects.filter(
            company=self.company,
            actor=self.admin,
            event_type='organization.created',
            target_id=str(organization.pk),
        ).exists())

        response = self.client.post(reverse('organization_edit', args=[organization.pk]), {
            'name': 'City Symphony',
            'short_name': 'CSO',
            'address': organization.address,
            'contact_name': organization.contact_name,
            'contact_email': organization.contact_email,
            'contact_phone': organization.contact_phone,
            'notes': organization.notes,
        })

        organization.refresh_from_db()
        self.assertRedirects(response, reverse('organization_detail', args=[organization.pk]))
        self.assertEqual(organization.name, 'City Symphony')
        self.assertTrue(AuditLog.objects.filter(
            company=self.company,
            event_type='organization.updated',
            target_id=str(organization.pk),
        ).exists())

    def test_deleting_organization_preserves_its_venues(self):
        organization = Organization.objects.create(company=self.company, name='Symphony')
        venue = Venue.objects.create(
            company=self.company,
            organization=organization,
            name='Concert Hall',
        )

        response = self.client.post(reverse('organization_delete', args=[organization.pk]))

        self.assertRedirects(response, reverse('organization_list'))
        self.assertFalse(Organization.objects.filter(pk=organization.pk).exists())
        venue.refresh_from_db()
        self.assertIsNone(venue.organization)
        self.assertTrue(AuditLog.objects.filter(
            company=self.company,
            event_type='organization.deleted',
            target_id=str(organization.pk),
        ).exists())

    def test_venue_create_rejects_another_companys_organization(self):
        other_organization = Organization.objects.create(
            company=self.other_company,
            name='Other Organization',
        )

        response = self.client.post(reverse('venue_create'), {
            'name': 'Wrong Venue',
            'short_name': '',
            'organization': other_organization.pk,
            'address': '',
            'on_site_contact': '',
            'parking_notes': '',
            'access_notes': '',
            'notes': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.assertFalse(Venue.objects.filter(name='Wrong Venue').exists())

    def test_venue_create_edit_and_delete_preserve_piano_location(self):
        organization = Organization.objects.create(company=self.company, name='Symphony')
        response = self.client.post(reverse('venue_create'), {
            'name': 'Concert Hall',
            'short_name': 'Hall',
            'organization': organization.pk,
            'address': '1 Music Way',
            'on_site_contact': '',
            'parking_notes': '',
            'access_notes': '',
            'notes': '',
        })
        venue = Venue.objects.get(name='Concert Hall')
        self.assertRedirects(response, reverse('venue_detail', args=[venue.pk]))
        self.assertEqual(venue.company, self.company)

        response = self.client.post(reverse('venue_edit', args=[venue.pk]), {
            'name': 'Grand Concert Hall',
            'short_name': 'Grand Hall',
            'organization': organization.pk,
            'address': venue.address,
            'on_site_contact': '',
            'parking_notes': '',
            'access_notes': '',
            'notes': '',
        })
        venue.refresh_from_db()
        self.assertRedirects(response, reverse('venue_detail', args=[venue.pk]))
        self.assertEqual(venue.name, 'Grand Concert Hall')

        piano = Piano.objects.create(
            company=self.company,
            venue=venue,
            name='Stage Piano',
            make='Steinway',
            piano_type=Piano.PianoType.GRAND,
        )
        response = self.client.post(reverse('venue_delete', args=[venue.pk]))

        self.assertRedirects(response, reverse('organization_detail', args=[organization.pk]))
        piano.refresh_from_db()
        self.assertIsNone(piano.venue)
        self.assertEqual(piano.venue_display, 'Grand Concert Hall')
        self.assertEqual(
            set(AuditLog.objects.filter(company=self.company).values_list('event_type', flat=True)),
            {'venue.created', 'venue.updated', 'venue.deleted'},
        )

    def test_piano_create_edit_and_deactivate_are_scoped_and_audited(self):
        venue = Venue.objects.create(company=self.company, name='Music School')

        response = self.client.post(
            reverse('piano_create'),
            self.piano_form_data(venue=str(venue.pk)),
        )
        piano = Piano.objects.get(name='Studio Piano')
        self.assertRedirects(response, reverse('piano_detail', args=[piano.pk]))
        self.assertEqual(piano.company, self.company)
        self.assertEqual(piano.venue, venue)

        response = self.client.post(
            reverse('piano_edit', args=[piano.pk]),
            self.piano_form_data(name='Teaching Studio Piano', venue=str(venue.pk)),
        )
        piano.refresh_from_db()
        self.assertRedirects(response, reverse('piano_detail', args=[piano.pk]))
        self.assertEqual(piano.name, 'Teaching Studio Piano')

        response = self.client.post(reverse('piano_deactivate', args=[piano.pk]))
        self.assertRedirects(response, reverse('piano_list'))
        piano.refresh_from_db()
        self.assertFalse(piano.is_active)
        self.assertEqual(
            list(AuditLog.objects.filter(company=self.company).order_by('created_at').values_list('event_type', flat=True)),
            ['piano.created', 'piano.updated', 'piano.deactivated'],
        )

    def test_core_edit_and_delete_views_hide_other_company_records(self):
        organization = Organization.objects.create(company=self.other_company, name='Hidden Org')
        venue = Venue.objects.create(company=self.other_company, name='Hidden Venue')
        piano = Piano.objects.create(
            company=self.other_company,
            name='Hidden Piano',
            make='Kawai',
            piano_type=Piano.PianoType.GRAND,
        )

        urls = [
            reverse('organization_edit', args=[organization.pk]),
            reverse('organization_delete', args=[organization.pk]),
            reverse('venue_edit', args=[venue.pk]),
            reverse('venue_delete', args=[venue.pk]),
            reverse('piano_edit', args=[piano.pk]),
            reverse('piano_deactivate', args=[piano.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)


class PianoCsvImportTests(CompanyAdminWebTestCase):
    def test_sample_download_has_expected_columns(self):
        response = self.client.get(reverse('piano_import_sample'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('piano_import_sample.csv', response['Content-Disposition'])
        rows = list(csv.reader(StringIO(response.content.decode('utf-8'))))
        self.assertEqual(rows[0][:5], ['name', 'make', 'model', 'serial_number', 'piano_type'])
        self.assertEqual(len(rows), 3)

    def test_valid_csv_creates_company_scoped_records_and_audit_log(self):
        upload = self.csv_upload([{
            'name': 'Concert Grand',
            'make': 'Steinway & Sons',
            'model': 'D',
            'serial_number': 'D123',
            'piano_type': 'Grand',
            'organization': 'City Symphony',
            'venue': 'Concert Hall',
            'section': 'Stage',
            'room': 'Main Stage',
            'year_built': '2015',
            'year_acquired': '2016',
            'notes': 'Primary instrument',
        }])

        response = self.client.post(reverse('piano_import'), {'csv_file': upload})

        self.assertRedirects(response, reverse('piano_list'))
        organization = Organization.objects.get(company=self.company, name='City Symphony')
        venue = Venue.objects.get(company=self.company, name='Concert Hall')
        piano = Piano.objects.get(company=self.company, name='Concert Grand')
        self.assertEqual(venue.organization, organization)
        self.assertEqual(piano.venue, venue)
        self.assertEqual(piano.year_built, 2015)
        audit = AuditLog.objects.get(company=self.company, event_type='piano.imported')
        self.assertEqual(audit.metadata, {'created_count': 1, 'error_count': 0})

    def test_import_does_not_reuse_records_from_another_company(self):
        other_organization = Organization.objects.create(
            company=self.other_company,
            name='Shared Organization',
        )
        Venue.objects.create(
            company=self.other_company,
            organization=other_organization,
            name='Shared Venue',
        )
        upload = self.csv_upload([{
            'name': 'Current Piano',
            'make': 'Yamaha',
            'model': '',
            'serial_number': '',
            'piano_type': 'Upright',
            'organization': 'Shared Organization',
            'venue': 'Shared Venue',
            'section': '',
            'room': '',
            'year_built': '',
            'year_acquired': '',
            'notes': '',
        }])

        self.client.post(reverse('piano_import'), {'csv_file': upload})

        current_organization = Organization.objects.get(
            company=self.company,
            name='Shared Organization',
        )
        current_venue = Venue.objects.get(company=self.company, name='Shared Venue')
        self.assertEqual(current_venue.organization, current_organization)
        self.assertEqual(Piano.objects.get(name='Current Piano').company, self.company)

    def test_invalid_row_is_skipped_without_discarding_valid_rows(self):
        base_row = {
            'make': 'Yamaha',
            'model': '',
            'serial_number': '',
            'piano_type': 'Upright',
            'organization': '',
            'venue': 'School',
            'section': '',
            'room': '',
            'year_acquired': '',
            'notes': '',
        }
        upload = self.csv_upload([
            {**base_row, 'name': 'Bad Year', 'year_built': 'not-a-year'},
            {**base_row, 'name': 'Valid Piano', 'year_built': '2018'},
        ])

        response = self.client.post(reverse('piano_import'), {'csv_file': upload}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Piano.objects.filter(company=self.company, name='Bad Year').exists())
        self.assertTrue(Piano.objects.filter(company=self.company, name='Valid Piano').exists())
        self.assertContains(response, '1 row(s) skipped')
        audit = AuditLog.objects.get(company=self.company, event_type='piano.imported')
        self.assertEqual(audit.metadata, {'created_count': 1, 'error_count': 1})

    def test_oversized_csv_is_rejected_before_processing(self):
        upload = SimpleUploadedFile(
            'too-large.csv',
            b'x' * ((5 * 1024 * 1024) + 1),
            content_type='text/csv',
        )

        response = self.client.post(reverse('piano_import'), {'csv_file': upload}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CSV file too large')
        self.assertEqual(Piano.objects.filter(company=self.company).count(), 0)
        self.assertFalse(AuditLog.objects.filter(event_type='piano.imported').exists())


class PartFlowTests(CompanyAdminWebTestCase):
    def test_part_create_and_edit_are_scoped_and_audited(self):
        response = self.client.post(reverse('part_create'), {
            'name': 'Bass String',
            'part_number': 'BS-1',
            'supplier': 'Piano Supply',
            'unit_cost': '12.50',
            'stock_quantity': '8',
            'reorder_threshold': '2',
        })

        part = Part.objects.get(name='Bass String')
        self.assertRedirects(response, reverse('part_list'))
        self.assertEqual(part.company, self.company)
        self.assertFalse(part.needs_reorder)

        response = self.client.post(reverse('part_edit', args=[part.pk]), {
            'name': 'Bass String Set',
            'part_number': 'BS-1',
            'supplier': 'Piano Supply',
            'unit_cost': '14.00',
            'stock_quantity': '2',
            'reorder_threshold': '2',
        })

        part.refresh_from_db()
        self.assertRedirects(response, reverse('part_list'))
        self.assertEqual(part.name, 'Bass String Set')
        self.assertTrue(part.needs_reorder)
        self.assertEqual(
            list(AuditLog.objects.filter(company=self.company).order_by('created_at').values_list('event_type', flat=True)),
            ['part.created', 'part.updated'],
        )

    def test_part_edit_hides_other_company_record(self):
        part = Part.objects.create(company=self.other_company, name='Hidden Part')

        self.assertEqual(self.client.get(reverse('part_edit', args=[part.pk])).status_code, 404)

    def test_logging_work_records_part_cost_and_decrements_stock(self):
        piano = Piano.objects.create(
            company=self.company,
            name='Service Piano',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
        )
        work_order = WorkOrder.objects.create(
            company=self.company,
            piano=piano,
            assigned_tech=self.admin,
            order_type=WorkOrder.OrderType.REQUEST,
        )
        part = Part.objects.create(
            company=self.company,
            name='Caster',
            unit_cost='18.75',
            stock_quantity=2,
            reorder_threshold=1,
        )
        other_part = Part.objects.create(
            company=self.other_company,
            name='Other Caster',
            unit_cost='99.00',
            stock_quantity=10,
        )

        response = self.client.post(reverse('workorder_log_work', args=[work_order.pk]), {
            'hours_worked': '1.25',
            'work_performed': 'Replaced casters',
            'notes': '',
            'part_id': [str(part.pk), str(other_part.pk)],
            'part_qty': ['3', '1'],
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('workorder_detail', args=[work_order.pk])))
        log = MaintenanceLog.objects.get(work_order=work_order)
        usage = PartUsed.objects.get(log=log)
        self.assertEqual(usage.company, self.company)
        self.assertEqual(usage.part, part)
        self.assertEqual(usage.quantity_used, 3)
        self.assertEqual(str(usage.cost_at_time), '18.75')
        self.assertFalse(PartUsed.objects.filter(part=other_part).exists())
        part.refresh_from_db()
        other_part.refresh_from_db()
        self.assertEqual(part.stock_quantity, 0)
        self.assertEqual(other_part.stock_quantity, 10)
        work_order.refresh_from_db()
        self.assertEqual(work_order.status, WorkOrder.Status.IN_PROGRESS)
        self.assertTrue(AuditLog.objects.filter(
            company=self.company,
            event_type='workorder.work_logged',
            target_id=str(work_order.pk),
        ).exists())


class ConditionReadingFlowTests(CompanyAdminWebTestCase):
    def setUp(self):
        super().setUp()
        self.piano = Piano.objects.create(
            company=self.company,
            name='Condition Piano',
            make='Steinway',
            piano_type=Piano.PianoType.GRAND,
        )

    def test_condition_reading_updates_pianos_current_state(self):
        response = self.client.post(
            reverse('condition_reading_create', args=[self.piano.pk]),
            {
                'overall_rating': ConditionLevel.GOOD,
                'regulation_condition': ConditionLevel.FAIR,
                'voicing_condition': '',
                'belly_condition': '',
                'soundboard_condition': '',
                'pinblock_condition': '',
                'strings_condition': '',
                'hammers_condition': '',
                'keys_condition': '',
                'pedals_condition': '',
                'case_condition': ConditionLevel.EXCELLENT,
                'pitch_before_cents': '-8.50',
                'pitch_after_cents': '0.25',
                'humidity_pct': '43.50',
                'temperature_f': '70.00',
                'notes': 'Stable after tuning',
            },
        )

        self.assertRedirects(response, reverse('piano_detail', args=[self.piano.pk]))
        reading = ConditionReading.objects.get(piano=self.piano)
        self.assertEqual(reading.company, self.company)
        self.assertEqual(reading.regulation_condition, ConditionLevel.FAIR)
        self.piano.refresh_from_db()
        self.assertEqual(self.piano.regulation_condition, ConditionLevel.FAIR)
        self.assertEqual(self.piano.case_condition, ConditionLevel.EXCELLENT)
        self.assertEqual(str(self.piano.current_pitch), '0.25')
        self.assertEqual(str(self.piano.current_humidity), '43.50')
        self.assertEqual(str(self.piano.current_temperature), '70.00')

    def test_new_reading_prefills_condition_and_environment_but_not_pitch(self):
        ConditionReading.objects.create(
            company=self.company,
            piano=self.piano,
            overall_rating=ConditionLevel.GOOD,
            regulation_condition=ConditionLevel.FAIR,
            pitch_before_cents='-12.00',
            pitch_after_cents='0.00',
            humidity_pct='45.00',
            temperature_f='71.00',
        )

        response = self.client.get(reverse('condition_reading_create', args=[self.piano.pk]))

        self.assertEqual(response.status_code, 200)
        initial = response.context['form'].initial
        self.assertEqual(initial['overall_rating'], ConditionLevel.GOOD)
        self.assertEqual(initial['regulation_condition'], ConditionLevel.FAIR)
        self.assertEqual(str(initial['humidity_pct']), '45.00')
        self.assertEqual(str(initial['temperature_f']), '71.00')
        self.assertNotIn('pitch_before_cents', initial)
        self.assertNotIn('pitch_after_cents', initial)

    def test_condition_create_hides_other_company_piano(self):
        other_piano = Piano.objects.create(
            company=self.other_company,
            name='Hidden Piano',
            make='Kawai',
            piano_type=Piano.PianoType.UPRIGHT,
        )

        response = self.client.get(reverse('condition_reading_create', args=[other_piano.pk]))

        self.assertEqual(response.status_code, 404)


class CoreRoleBoundaryTests(CompanyAdminWebTestCase):
    def setUp(self):
        super().setUp()
        self.organization = Organization.objects.create(company=self.company, name='Symphony')
        self.venue = Venue.objects.create(
            company=self.company,
            organization=self.organization,
            name='Concert Hall',
        )
        self.piano = Piano.objects.create(
            company=self.company,
            venue=self.venue,
            name='Stage Piano',
            make='Steinway',
            piano_type=Piano.PianoType.GRAND,
        )
        self.part = Part.objects.create(company=self.company, name='Hammer Felt')
        self.technician = Technician.objects.create_user(
            username='technician',
            password='StrongPass123',
        )
        CompanyMembership.objects.create(
            company=self.company,
            user=self.technician,
            role_admin=False,
            role_technician=True,
        )

    def login_as_technician(self):
        self.client.force_login(self.technician)
        session = self.client.session
        session['active_company_id'] = self.company.pk
        session.save()

    def test_anonymous_user_is_redirected_from_company_data(self):
        self.client.logout()
        urls = [
            reverse('organization_list'),
            reverse('venue_detail', args=[self.venue.pk]),
            reverse('piano_detail', args=[self.piano.pk]),
            reverse('condition_reading_create', args=[self.piano.pk]),
            reverse('part_list'),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response.url)

    def test_technician_can_read_core_records_and_record_conditions(self):
        self.login_as_technician()
        readable_urls = [
            reverse('organization_list'),
            reverse('organization_detail', args=[self.organization.pk]),
            reverse('venue_list'),
            reverse('venue_detail', args=[self.venue.pk]),
            reverse('piano_list'),
            reverse('piano_detail', args=[self.piano.pk]),
            reverse('condition_reading_create', args=[self.piano.pk]),
        ]

        for url in readable_urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

        response = self.client.post(
            reverse('condition_reading_create', args=[self.piano.pk]),
            {
                'overall_rating': ConditionLevel.GOOD,
                'regulation_condition': '',
                'voicing_condition': '',
                'belly_condition': '',
                'soundboard_condition': '',
                'pinblock_condition': '',
                'strings_condition': '',
                'hammers_condition': '',
                'keys_condition': '',
                'pedals_condition': '',
                'case_condition': '',
                'pitch_before_cents': '',
                'pitch_after_cents': '',
                'humidity_pct': '42.00',
                'temperature_f': '',
                'notes': 'Technician reading',
            },
        )
        self.assertRedirects(response, reverse('piano_detail', args=[self.piano.pk]))
        self.assertTrue(ConditionReading.objects.filter(
            company=self.company,
            piano=self.piano,
            notes='Technician reading',
        ).exists())

    def test_technician_cannot_reach_admin_only_core_actions(self):
        self.login_as_technician()
        admin_only_urls = [
            reverse('organization_create'),
            reverse('organization_edit', args=[self.organization.pk]),
            reverse('organization_delete', args=[self.organization.pk]),
            reverse('venue_create'),
            reverse('venue_edit', args=[self.venue.pk]),
            reverse('venue_delete', args=[self.venue.pk]),
            reverse('piano_create'),
            reverse('piano_edit', args=[self.piano.pk]),
            reverse('piano_deactivate', args=[self.piano.pk]),
            reverse('piano_import'),
            reverse('piano_import_sample'),
            reverse('part_list'),
            reverse('part_create'),
            reverse('part_edit', args=[self.part.pk]),
        ]

        for url in admin_only_urls:
            with self.subTest(method='GET', url=url):
                self.assertRedirects(self.client.get(url), reverse('dashboard'))
            with self.subTest(method='POST', url=url):
                self.assertRedirects(self.client.post(url, {}), reverse('dashboard'))

        self.organization.refresh_from_db()
        self.venue.refresh_from_db()
        self.piano.refresh_from_db()
        self.part.refresh_from_db()
        self.assertTrue(self.piano.is_active)
        self.assertEqual(Organization.objects.filter(company=self.company).count(), 1)
        self.assertEqual(Venue.objects.filter(company=self.company).count(), 1)
        self.assertEqual(Piano.objects.filter(company=self.company).count(), 1)
        self.assertEqual(Part.objects.filter(company=self.company).count(), 1)
        self.assertEqual(AuditLog.objects.filter(company=self.company).count(), 0)
