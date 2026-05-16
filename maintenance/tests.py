import os
import tempfile
from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Company,
    CompanyInvitation,
    CompanyMembership,
    CompanySettings,
    MaintenanceSchedule,
    Organization,
    Photo,
    Piano,
    Technician,
    Venue,
    WorkOrder,
)
from .audit import log_audit_event
from .services import generate_scheduled_work_orders


class CompanyScopedTestCase(TestCase):
    company_name = 'Test Company'
    company_slug = 'test-company'

    def setUp(self):
        super().setUp()
        self.company = Company.objects.create(
            name=self.company_name,
            slug=self.company_slug,
        )

    def create_user(self, username, *, password='StrongPass123', company=None, membership=True, **kwargs):
        company = company or self.company
        role_admin = kwargs.pop('role_admin', False)
        role_technician = kwargs.pop('role_technician', True)
        user = Technician.objects.create_user(
            username=username,
            password=password,
            role_admin=False,
            role_technician=False,
            **kwargs,
        )
        if membership:
            CompanyMembership.objects.create(
                company=company,
                user=user,
                role_admin=role_admin,
                role_technician=role_technician,
                is_active=user.is_active,
            )
        return user

    def create_piano(self, *, company=None, **kwargs):
        company = company or self.company
        defaults = {
            'company': company,
            'name': 'Test Piano',
            'make': 'Yamaha',
            'piano_type': Piano.PianoType.UPRIGHT,
        }
        defaults.update(kwargs)
        return Piano.objects.create(**defaults)

    def login_user(self, user, *, company=None):
        self.client.force_login(user)
        session = self.client.session
        session['active_company_id'] = (company or self.company).pk
        session.save()

class AuthEntryTests(TestCase):
    def test_login_page_does_not_offer_public_signup(self):
        response = self.client.get(reverse('login'))

        self.assertContains(response, 'Forgot your password?')
        self.assertContains(response, 'Contact your company admin or Overtone support.')
        self.assertNotContains(response, 'Request an account')


class QRCodeRoutingTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.piano = Piano.objects.create(
            company=self.company,
            name='Studio Upright',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
        )
        self.url = reverse('maintenance-request-form', args=[self.piano.qr_code_token])

    def test_anonymous_qr_visit_shows_maintenance_request_form(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'maintenance/maintenance_request_form.html')
        self.assertContains(response, 'Studio Upright')

    def test_logged_in_qr_visit_redirects_to_piano_detail(self):
        user = self.create_user('qrtech')
        self.login_user(user)

        response = self.client.get(self.url)

        self.assertRedirects(response, reverse('piano_detail', args=[self.piano.pk]))


class PhotoDeletionTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.media_root = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root.name)
        self.settings_override.enable()
        self.piano = Piano.objects.create(
            company=self.company,
            name='Photo Piano',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
        )

    def tearDown(self):
        self.settings_override.disable()
        self.media_root.cleanup()

    def _create_photo(self, is_profile_photo=False):
        return Photo.objects.create(
            company=self.company,
            piano=self.piano,
            image=SimpleUploadedFile(
                'photo.jpg',
                b'test image content',
                content_type='image/jpeg',
            ),
            is_profile_photo=is_profile_photo,
        )

    def test_technician_can_delete_piano_photo(self):
        user = self.create_user('phototech')
        photo = self._create_photo()
        image_path = photo.image.path
        self.login_user(user)

        response = self.client.post(reverse(
            'piano_photo_delete',
            args=[self.piano.pk, photo.pk],
        ))

        self.assertRedirects(response, reverse('piano_detail', args=[self.piano.pk]))
        self.assertFalse(Photo.objects.filter(pk=photo.pk).exists())
        self.assertFalse(os.path.exists(image_path))

    def test_admin_can_delete_piano_photo(self):
        user = self.create_user('photoadmin', role_admin=True, role_technician=False)
        photo = self._create_photo()
        self.login_user(user)

        response = self.client.post(reverse(
            'piano_photo_delete',
            args=[self.piano.pk, photo.pk],
        ))

        self.assertRedirects(response, reverse('piano_detail', args=[self.piano.pk]))
        self.assertFalse(Photo.objects.filter(pk=photo.pk).exists())

    def test_deleting_profile_photo_promotes_next_photo(self):
        user = self.create_user('profilephototech')
        profile_photo = self._create_photo(is_profile_photo=True)
        next_photo = self._create_photo()
        self.login_user(user)

        self.client.post(reverse(
            'piano_photo_delete',
            args=[self.piano.pk, profile_photo.pk],
        ))

        next_photo.refresh_from_db()
        self.assertTrue(next_photo.is_profile_photo)

    def test_piano_detail_shows_photo_activity(self):
        user = self.create_user('photoauditor')
        self._create_photo()
        log_audit_event(
            company=self.company,
            actor=user,
            event_type='piano.photo_uploaded',
            target=self.piano,
            message='Uploaded 1 photo(s).',
        )
        self.login_user(user)

        response = self.client.get(reverse('piano_detail', args=[self.piano.pk]))

        self.assertContains(response, 'Recent Activity')
        self.assertContains(response, 'Photo uploaded by photoauditor')

    def test_company_member_can_view_photo_through_authorized_endpoint(self):
        user = self.create_user('photoviewer')
        photo = self._create_photo()
        self.login_user(user)

        response = self.client.get(reverse('photo_file', args=[photo.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')

    def test_user_from_other_company_cannot_view_photo(self):
        other_company = Company.objects.create(name='Other Co', slug='other-co')
        outsider = self.create_user('outsider', company=other_company)
        photo = self._create_photo()
        self.login_user(outsider, company=other_company)

        response = self.client.get(reverse('photo_file', args=[photo.pk]))

        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_from_photo_endpoint(self):
        photo = self._create_photo()

        response = self.client.get(reverse('photo_file', args=[photo.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_photo_company_must_match_related_objects(self):
        other_company = Company.objects.create(name='Mismatch Co', slug='mismatch-co')
        other_piano = self.create_piano(company=other_company, name='Mismatch Piano')

        with self.assertRaises(ValidationError):
            Photo.objects.create(
                company=self.company,
                piano=other_piano,
                image=SimpleUploadedFile(
                    'bad-photo.jpg',
                    b'test image content',
                    content_type='image/jpeg',
                ),
            )

    def test_photo_work_order_and_piano_must_agree(self):
        other_piano = self.create_piano(name='Other Piano')
        work_order = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )

        with self.assertRaises(ValidationError):
            Photo.objects.create(
                company=self.company,
                piano=other_piano,
                work_order=work_order,
                image=SimpleUploadedFile(
                    'bad-link.jpg',
                    b'test image content',
                    content_type='image/jpeg',
                ),
            )


class WorkOrderStateTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.tech = self.create_user(
            'state-tech',
            first_name='State',
            last_name='Tech',
        )
        self.piano = Piano.objects.create(
            company=self.company,
            name='State Piano',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
        )
        self.login_user(self.tech)

    def test_workorder_list_uses_task_type_as_order_type(self):
        WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.tech,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Tuning',
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )

        response = self.client.get(reverse('workorder_list'))

        self.assertContains(response, 'Order Type')
        self.assertContains(response, 'Tuning')

    def test_schedule_link_preserves_return_url_on_detail_back_link(self):
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.tech,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Voicing',
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )

        response = self.client.get(
            reverse('workorder_detail', args=[wo.pk]),
            {'return_url': reverse('schedule')},
        )

        self.assertContains(response, f'href="{reverse("schedule")}"')

    def test_schedule_cards_link_back_to_schedule(self):
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.tech,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Voicing',
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )

        response = self.client.get(reverse('schedule'))

        self.assertContains(
            response,
            f'/work-orders/{wo.pk}/?return_url=/schedule/',
        )

    def test_piano_workorder_tab_links_to_workorder_detail(self):
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.tech,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Regulation',
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )

        response = self.client.get(reverse('piano_tab', args=[self.piano.pk, 'work-orders']))

        self.assertContains(response, f'/work-orders/{wo.pk}/?return_url=')
        self.assertContains(response, f'WO-{wo.pk}')

    def test_unassigned_workorder_is_assigned_to_completing_user(self):
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )

        response = self.client.post(reverse('workorder_complete', args=[wo.pk]), {
            'hours_worked': '1.25',
            'work_performed': 'Completed requested work.',
            'notes': '',
        })

        self.assertEqual(response.status_code, 302)
        wo.refresh_from_db()
        self.assertEqual(wo.assigned_tech, self.tech)
        self.assertEqual(wo.status, WorkOrder.Status.COMPLETE)

    def test_completed_workorder_detail_has_edit_and_reopen_actions(self):
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.tech,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Tuning',
            status=WorkOrder.Status.COMPLETE,
            priority=WorkOrder.Priority.NORMAL,
            completed_date='2026-05-12',
        )

        response = self.client.get(reverse('workorder_detail', args=[wo.pk]))

        self.assertContains(response, reverse('workorder_edit', args=[wo.pk]))
        self.assertContains(response, reverse('workorder_reopen', args=[wo.pk]))
        self.assertContains(response, 'Reopen')

    def test_delete_preserves_schedule_return_url(self):
        CompanyMembership.objects.filter(company=self.company, user=self.tech).update(role_admin=True)
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.tech,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Cleaning',
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )

        detail_response = self.client.get(
            reverse('workorder_detail', args=[wo.pk]),
            {'return_url': reverse('schedule')},
        )
        self.assertContains(
            detail_response,
            f'{reverse("workorder_delete", args=[wo.pk])}?return_url=/schedule/',
        )

        delete_response = self.client.post(
            reverse('workorder_delete', args=[wo.pk]),
            {'return_url': reverse('schedule')},
        )

        self.assertRedirects(delete_response, reverse('schedule'))
        self.assertFalse(WorkOrder.objects.filter(pk=wo.pk).exists())

    def test_unsafe_return_url_falls_back_to_workorder_list(self):
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.tech,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Tuning',
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )

        response = self.client.get(
            reverse('workorder_detail', args=[wo.pk]),
            {'return_url': 'https://example.com/steal-state'},
        )

        self.assertContains(response, f'href="{reverse("workorder_list")}"')
        self.assertNotContains(response, 'https://example.com/steal-state')

    def test_workorder_detail_shows_recent_activity(self):
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.tech,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Tuning',
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )
        log_audit_event(
            company=self.company,
            actor=self.tech,
            event_type='workorder.updated',
            target=wo,
            message='Adjusted description and due date.',
        )

        response = self.client.get(reverse('workorder_detail', args=[wo.pk]))

        self.assertContains(response, 'Recent Activity')
        self.assertContains(response, 'Updated by State Tech')
        self.assertContains(response, 'Adjusted description and due date.')

    def test_reopen_completed_workorder_clears_completed_date(self):
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.tech,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Tuning',
            status=WorkOrder.Status.COMPLETE,
            priority=WorkOrder.Priority.NORMAL,
            completed_date='2026-05-12',
        )

        response = self.client.post(reverse('workorder_reopen', args=[wo.pk]))

        self.assertEqual(response.status_code, 302)
        wo.refresh_from_db()
        self.assertEqual(wo.status, WorkOrder.Status.IN_PROGRESS)
        self.assertIsNone(wo.completed_date)

    def test_edit_completed_workorder_updates_details(self):
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.tech,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Tuning',
            status=WorkOrder.Status.COMPLETE,
            priority=WorkOrder.Priority.NORMAL,
            completed_date='2026-05-12',
            description='Original',
        )

        response = self.client.post(reverse('workorder_edit', args=[wo.pk]), {
            'piano': self.piano.pk,
            'order_type': WorkOrder.OrderType.PREVENTIVE,
            'task_type': 'Voicing',
            'priority': WorkOrder.Priority.HIGH,
            'assigned_tech': self.tech.pk,
            'description': 'Updated after review',
            'due_date': '',
        })

        self.assertEqual(response.status_code, 302)
        wo.refresh_from_db()
        self.assertEqual(wo.task_type, 'Voicing')
        self.assertEqual(wo.priority, WorkOrder.Priority.HIGH)
        self.assertEqual(wo.description, 'Updated after review')


class ScheduledWorkOrderGenerationTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.today = date(2026, 5, 12)
        self.piano = Piano.objects.create(
            company=self.company,
            name='Generator Piano',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
            next_tuning_due=self.today - timedelta(days=1),
            next_regulation_due=self.today + timedelta(days=30),
            next_voicing_due=None,
            next_cleaning_due=None,
        )

    def test_service_creates_built_in_due_work_order(self):
        result = generate_scheduled_work_orders(today=self.today)

        self.assertGreaterEqual(result.created, 1)
        self.assertTrue(WorkOrder.objects.filter(
            piano=self.piano,
            task_type='Tuning',
            due_date=self.today - timedelta(days=1),
            status=WorkOrder.Status.OPEN,
        ).exists())

    def test_service_does_not_duplicate_open_work_order(self):
        WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Tuning',
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            due_date=self.today,
        )

        generate_scheduled_work_orders(today=self.today)

        self.assertEqual(WorkOrder.objects.filter(
            piano=self.piano,
            task_type='Tuning',
            status__in=[WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS],
        ).count(), 1)

    def test_service_creates_custom_schedule_work_order(self):
        schedule = MaintenanceSchedule.objects.create(
            company=self.company,
            piano=self.piano,
            task_name='Annual inspection',
            task_type='Inspection',
            interval_days=365,
            warning_days_before=14,
            last_service_date=self.today - timedelta(days=360),
        )

        generate_scheduled_work_orders(today=self.today)

        self.assertTrue(WorkOrder.objects.filter(
            piano=self.piano,
            schedule=schedule,
            task_type='Inspection',
            due_date=self.today + timedelta(days=5),
        ).exists())

    def test_dry_run_does_not_create_work_orders(self):
        result = generate_scheduled_work_orders(today=self.today, dry_run=True)

        self.assertGreaterEqual(result.created, 1)
        self.assertFalse(WorkOrder.objects.filter(piano=self.piano).exists())

    def test_management_command_uses_generation_service(self):
        out = StringIO()

        call_command('generate_work_orders', '--dry-run', stdout=out)

        self.assertIn('DRY RUN', out.getvalue())
        self.assertIn('Done. Created:', out.getvalue())

    def test_generation_can_be_limited_to_a_single_company(self):
        other_company = Company.objects.create(name='Other Company', slug='other-company')
        Piano.objects.create(
            company=other_company,
            name='Other Piano',
            make='Steinway',
            piano_type=Piano.PianoType.GRAND,
            next_tuning_due=self.today - timedelta(days=1),
        )

        result = generate_scheduled_work_orders(today=self.today, company=self.company)

        self.assertGreaterEqual(result.created, 1)
        self.assertTrue(WorkOrder.objects.filter(company=self.company).exists())
        self.assertFalse(WorkOrder.objects.filter(company=other_company).exists())

    def test_management_command_can_target_company_by_slug(self):
        other_company = Company.objects.create(name='Other Company', slug='other-company')
        Piano.objects.create(
            company=other_company,
            name='Other Piano',
            make='Steinway',
            piano_type=Piano.PianoType.GRAND,
            next_tuning_due=self.today - timedelta(days=1),
        )
        out = StringIO()

        call_command('generate_work_orders', '--company-slug', self.company.slug, stdout=out)

        self.assertIn(f'Target company: {self.company.name}', out.getvalue())
        self.assertTrue(WorkOrder.objects.filter(company=self.company).exists())
        self.assertFalse(WorkOrder.objects.filter(company=other_company).exists())


class ScheduleViewTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.tech = self.create_user('scheduletech')
        self.piano = Piano.objects.create(
            company=self.company,
            name='Schedule Piano',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
        )
        self.login_user(self.tech)

    def _work_order(self, task_type, due_date=None):
        return WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type=task_type,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            due_date=due_date,
        )

    def test_schedule_groups_active_work_by_maintenance_category(self):
        tuning = self._work_order('Tuning')
        regulation = self._work_order('Regulation')
        self._work_order('Inspection')

        response = self.client.get(reverse('schedule'))

        labels = [column['label'] for column in response.context['schedule_columns']]
        self.assertEqual(labels, [
            'Pianos Needing Tuning',
            'Pianos Needing Regulation',
            'Pianos Needing Voicing',
            'Pianos Needing Cleaning',
        ])
        self.assertContains(response, f'WO-{tuning.pk}')
        self.assertContains(response, f'WO-{regulation.pk}')
        self.assertNotContains(response, 'Inspection')
        self.assertContains(response, 'class="schedule-mobile-tab active"')
        self.assertContains(response, 'data-schedule-tab="col-tuning"')

    def test_schedule_due_filter_applies_before_category_grouping(self):
        today = date.today()
        overdue_tuning = self._work_order('Tuning', today - timedelta(days=1))
        next_30_tuning = self._work_order('Tuning', today + timedelta(days=10))
        self._work_order('Tuning', today + timedelta(days=45))
        self._work_order('Tuning', None)

        response = self.client.get(reverse('schedule'), {'due': 'next-30'})

        self.assertContains(response, 'Next 30 Days')
        self.assertNotContains(response, f'WO-{overdue_tuning.pk}')
        self.assertContains(response, f'WO-{next_30_tuning.pk}')
        self.assertEqual(response.context['due_filter'], 'next-30')

    def test_schedule_due_filter_hx_request_returns_partial(self):
        self._work_order('Tuning', date.today() + timedelta(days=10))

        response = self.client.get(
            reverse('schedule'),
            {'due': 'next-30'},
            HTTP_HX_REQUEST='true',
        )

        self.assertContains(response, 'id="schedule-results"')
        self.assertContains(response, 'hx-get="/schedule/?due=overdue"')
        self.assertNotContains(response, '<h1>Schedule</h1>')

    def test_schedule_filters_by_organization_and_venue(self):
        org_a = Organization.objects.create(company=self.company, name='Org A')
        org_b = Organization.objects.create(company=self.company, name='Org B')
        venue_a = Venue.objects.create(company=self.company, name='Venue A', organization=org_a)
        venue_b = Venue.objects.create(company=self.company, name='Venue B', organization=org_b)
        self.piano.venue = venue_a
        self.piano.save(update_fields=['venue'])
        other_piano = Piano.objects.create(
            company=self.company,
            name='Other Schedule Piano',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
            venue=venue_b,
        )
        matching = self._work_order('Tuning')
        excluded = WorkOrder.objects.create(
            company=self.company,
            piano=other_piano,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Tuning',
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )

        response = self.client.get(reverse('schedule'), {
            'org': org_a.pk,
            'venue': venue_a.pk,
        })

        self.assertContains(response, f'WO-{matching.pk}')
        self.assertNotContains(response, f'WO-{excluded.pk}')
        self.assertEqual(response.context['org_filter'], str(org_a.pk))
        self.assertEqual(response.context['venue_filter'], str(venue_a.pk))

    def test_schedule_workorder_return_url_preserves_filters(self):
        org = Organization.objects.create(company=self.company, name='Return Org')
        venue = Venue.objects.create(company=self.company, name='Return Venue', organization=org)
        self.piano.venue = venue
        self.piano.save(update_fields=['venue'])
        wo = self._work_order('Cleaning')

        response = self.client.get(reverse('schedule'), {
            'due': 'no-date',
            'org': org.pk,
            'venue': venue.pk,
        })

        self.assertContains(
            response,
            (
                f'/work-orders/{wo.pk}/?return_url='
                f'/schedule/%3Fdue%3Dno-date%26org%3D{org.pk}%26venue%3D{venue.pk}'
            ),
        )


class TechnicianManagementTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.create_user(
            'admin',
            first_name='Admin',
            last_name='User',
            role_admin=True,
            role_technician=True,
        )
        self.login_user(self.admin)

    def test_admin_can_create_active_user_with_roles(self):
        response = self.client.post(reverse('technician_create'), {
            'username': 'newtech',
            'first_name': 'New',
            'last_name': 'Tech',
            'email': 'newtech@example.com',
            'is_active': 'on',
            'role_technician': 'on',
            'role_admin': 'on',
            'password1': 'StrongPass123',
            'password2': 'StrongPass123',
        })

        self.assertRedirects(response, reverse('technician_list'))
        user = Technician.objects.get(username='newtech')
        self.assertTrue(user.is_active)
        self.assertTrue(user.role_admin)
        self.assertTrue(user.role_technician)

    def test_admin_cannot_remove_own_admin_access(self):
        response = self.client.post(reverse('technician_edit', args=[self.admin.pk]), {
            'username': self.admin.username,
            'first_name': self.admin.first_name,
            'last_name': self.admin.last_name,
            'email': self.admin.email,
            'is_active': 'on',
            'role_technician': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.role_admin)

    def test_admin_can_deactivate_company_membership_without_disabling_account(self):
        tech = self.create_user(
            'sharedtech',
            first_name='Shared',
            last_name='Tech',
        )
        second_company = Company.objects.create(name='Second Company', slug='second-company')
        CompanyMembership.objects.create(
            company=second_company,
            user=tech,
            role_admin=False,
            role_technician=True,
            is_active=True,
        )

        response = self.client.post(reverse('technician_edit', args=[tech.pk]), {
            'username': tech.username,
            'first_name': tech.first_name,
            'last_name': tech.last_name,
            'email': tech.email,
            'role_technician': 'on',
        })

        self.assertRedirects(response, reverse('technician_list'))
        tech.refresh_from_db()
        current_membership = CompanyMembership.objects.get(company=self.company, user=tech)
        other_membership = CompanyMembership.objects.get(company=second_company, user=tech)
        self.assertTrue(tech.is_active)
        self.assertFalse(current_membership.is_active)
        self.assertTrue(other_membership.is_active)

    def test_inactive_company_membership_still_appears_on_technician_list(self):
        tech = self.create_user(
            'inactivecompanytech',
            first_name='Inactive',
            last_name='Member',
        )
        membership = CompanyMembership.objects.get(company=self.company, user=tech)
        membership.is_active = False
        membership.save()

        response = self.client.get(reverse('technician_list'))

        self.assertContains(response, 'inactivecompanytech')
        self.assertContains(response, 'Inactive in Company')

    def test_admin_can_reactivate_company_membership_from_list(self):
        tech = self.create_user(
            'reactivatetech',
            first_name='Reactivate',
            last_name='Member',
        )
        membership = CompanyMembership.objects.get(company=self.company, user=tech)
        membership.is_active = False
        membership.save()

        response = self.client.post(reverse('technician_toggle_membership', args=[tech.pk]))

        self.assertRedirects(response, reverse('technician_list'))
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)

    def test_admin_cannot_deactivate_own_company_membership_from_list(self):
        response = self.client.post(reverse('technician_toggle_membership', args=[self.admin.pk]))

        self.assertRedirects(response, reverse('technician_list'))
        membership = CompanyMembership.objects.get(company=self.company, user=self.admin)
        self.assertTrue(membership.is_active)

    def test_technician_list_explains_cross_company_inactive_state(self):
        tech = self.create_user(
            'multicotech',
            first_name='Multi',
            last_name='Company',
        )
        second_company = Company.objects.create(name='Partner Company', slug='partner-company')
        CompanyMembership.objects.create(
            company=second_company,
            user=tech,
            role_admin=False,
            role_technician=True,
            is_active=True,
        )
        membership = CompanyMembership.objects.get(company=self.company, user=tech)
        membership.is_active = False
        membership.save()

        response = self.client.get(reverse('technician_list'))

        self.assertContains(response, 'Account stays available for other companies.')


class WorkOrderAssignmentTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.tech = self.create_user(
            'tech',
            first_name='Test',
            last_name='Tech',
        )
        self.other_tech = self.create_user(
            'othertech',
            first_name='Other',
            last_name='Tech',
        )
        self.login_user(self.tech)

    def test_technician_can_assign_self_to_unassigned_work_order(self):
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.create_piano(name='Assignable Piano'),
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Unassigned request',
        )

        response = self.client.post(reverse('workorder_assign', args=[wo.pk]), {
            'assign_action': 'assign_self',
        })

        self.assertEqual(response.status_code, 200)
        wo.refresh_from_db()
        self.assertEqual(wo.assigned_tech, self.tech)
        self.assertEqual(wo.status, WorkOrder.Status.IN_PROGRESS)

    def test_technician_cannot_take_work_order_assigned_to_someone_else(self):
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.create_piano(name='Assigned Piano'),
            assigned_tech=self.other_tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.IN_PROGRESS,
            priority=WorkOrder.Priority.NORMAL,
            description='Already assigned request',
        )

        response = self.client.post(reverse('workorder_assign', args=[wo.pk]), {
            'assign_action': 'assign_self',
        })

        self.assertEqual(response.status_code, 200)
        wo.refresh_from_db()
        self.assertEqual(wo.assigned_tech, self.other_tech)


class TechnicianDashboardTests(TestCase):
    def test_dashboard_shows_only_active_work_orders_assigned_to_technician(self):
        company = Company.objects.create(name='Dashboard Co', slug='dashboard-co')
        tech = Technician.objects.create_user(username='dashboardtech', password='StrongPass123', role_admin=False, role_technician=True)
        other_tech = Technician.objects.create_user(username='otherdashboardtech', password='StrongPass123', role_admin=False, role_technician=True)
        CompanyMembership.objects.create(company=company, user=tech, role_admin=False, role_technician=True, is_active=True)
        CompanyMembership.objects.create(company=company, user=other_tech, role_admin=False, role_technician=True, is_active=True)
        assigned_open = WorkOrder.objects.create(
            company=company,
            assigned_tech=tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Assigned open',
        )
        assigned_in_progress = WorkOrder.objects.create(
            company=company,
            assigned_tech=tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.IN_PROGRESS,
            priority=WorkOrder.Priority.NORMAL,
            description='Assigned in progress',
        )
        WorkOrder.objects.create(
            company=company,
            assigned_tech=tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.COMPLETE,
            priority=WorkOrder.Priority.NORMAL,
            description='Assigned complete',
        )
        WorkOrder.objects.create(
            company=company,
            assigned_tech=other_tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Other tech open',
        )
        WorkOrder.objects.create(
            company=company,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Unassigned open',
        )

        self.client.force_login(tech)
        session = self.client.session
        session['active_company_id'] = company.pk
        session.save()
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'My Work Orders')
        self.assertQuerySetEqual(
            response.context['dashboard_work_orders'],
            [assigned_in_progress, assigned_open],
            ordered=False,
        )


class AdminOnboardingTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.create_user(
            'setupadmin',
            role_admin=True,
            role_technician=True,
            email='setup@example.com',
        )
        self.login_user(self.admin)

    def test_dashboard_shows_setup_progress_for_incomplete_company(self):
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'Workspace Setup')
        self.assertContains(response, 'Complete company profile')
        self.assertContains(response, 'Add your team')
        self.assertContains(response, 'Add your first piano')

    def test_setup_progress_disappears_when_core_records_exist(self):
        settings_obj = CompanySettings.load_for_company(self.company)
        settings_obj.company_name = self.company.name
        settings_obj.email = 'ops@example.com'
        settings_obj.save()

        teammate = self.create_user('setuptech')
        organization = Organization.objects.create(company=self.company, name='Setup Org')
        venue = Venue.objects.create(company=self.company, organization=organization, name='Setup Venue')
        Piano.objects.create(
            company=self.company,
            venue=venue,
            name='Setup Piano',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
        )

        response = self.client.get(reverse('dashboard'))

        self.assertNotContains(response, 'Workspace Setup')
        self.assertTrue(
            CompanyMembership.objects.filter(company=self.company, user=teammate).exists()
        )


class WorkOrderListSortingTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.tech = self.create_user('sorttech')
        self.login_user(self.tech)
        self.first_wo = WorkOrder.objects.create(
            company=self.company,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='First work order',
        )
        self.second_wo = WorkOrder.objects.create(
            company=self.company,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Second work order',
        )
        self.completed_wo = WorkOrder.objects.create(
            company=self.company,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.COMPLETE,
            priority=WorkOrder.Priority.NORMAL,
            description='Completed work order',
            completed_date=date.today(),
        )

    def test_work_order_list_sorts_by_clicked_column_and_direction(self):
        response = self.client.get(reverse('workorder_list'), {
            'sort': 'id',
            'dir': 'asc',
        })

        self.assertQuerySetEqual(
            response.context['work_orders'],
            [self.first_wo, self.second_wo, self.completed_wo],
        )

        response = self.client.get(reverse('workorder_list'), {
            'sort': 'id',
            'dir': 'desc',
        })

        self.assertQuerySetEqual(
            response.context['work_orders'],
            [self.completed_wo, self.second_wo, self.first_wo],
        )

    def test_htmx_sort_returns_work_order_table_partial(self):
        response = self.client.get(
            reverse('workorder_list'),
            {'sort': 'id', 'dir': 'asc'},
            HTTP_HX_REQUEST='true',
        )

        self.assertContains(response, 'id="workorder-results"')
        self.assertContains(response, 'hx-get="?sort=id&amp;dir=desc"')
        self.assertNotContains(response, '<h1>Work Orders</h1>')

    def test_completed_date_filter_limits_results(self):
        response = self.client.get(reverse('workorder_list'), {
            'completed_from': date.today().isoformat(),
            'completed_to': date.today().isoformat(),
        })

        self.assertContains(response, f'WO-{self.completed_wo.pk}')
        self.assertNotContains(response, f'WO-{self.first_wo.pk}')
        self.assertEqual(response.context['completed_from'], date.today().isoformat())

    def test_export_csv_uses_current_filters(self):
        response = self.client.get(reverse('workorder_export_csv'), {
            'completed_from': date.today().isoformat(),
            'completed_to': date.today().isoformat(),
        })

        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn(f'WO-{self.completed_wo.pk}', content)
        self.assertNotIn(f'WO-{self.first_wo.pk}', content)


class CompanySwitchingTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.company_a = Company.objects.create(name='Alpha Piano', slug='alpha-piano')
        self.company_b = Company.objects.create(name='Bravo Piano', slug='bravo-piano')
        self.user = Technician.objects.create_user(
            username='multicompany',
            password='StrongPass123',
            role_admin=False,
            role_technician=False,
        )
        CompanyMembership.objects.create(
            company=self.company_a,
            user=self.user,
            role_admin=True,
            role_technician=True,
        )
        CompanyMembership.objects.create(
            company=self.company_b,
            user=self.user,
            role_admin=True,
            role_technician=True,
        )
        self.alpha_piano = Piano.objects.create(
            company=self.company_a,
            name='Alpha Piano A',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
        )
        self.bravo_piano = Piano.objects.create(
            company=self.company_b,
            name='Bravo Piano B',
            make='Steinway',
            piano_type=Piano.PianoType.GRAND,
        )
        self.client.force_login(self.user)

    def test_company_switcher_changes_visible_pianos(self):
        session = self.client.session
        session['active_company_id'] = self.company_a.pk
        session.save()

        response = self.client.get(reverse('piano_list'))
        self.assertContains(response, 'Alpha Piano A')
        self.assertNotContains(response, 'Bravo Piano B')

        response = self.client.post(reverse('switch_company'), {
            'company_id': self.company_b.pk,
            'next': reverse('piano_list'),
        })
        self.assertRedirects(response, reverse('piano_list'))

        response = self.client.get(reverse('piano_list'))
        self.assertContains(response, 'Bravo Piano B')
        self.assertNotContains(response, 'Alpha Piano A')

    def test_switch_company_ignores_companies_without_membership(self):
        outsider_company = Company.objects.create(name='Outsider', slug='outsider')
        session = self.client.session
        session['active_company_id'] = self.company_a.pk
        session.save()

        response = self.client.post(reverse('switch_company'), {
            'company_id': outsider_company.pk,
            'next': reverse('piano_list'),
        })

        self.assertRedirects(response, reverse('piano_list'))
        response = self.client.get(reverse('piano_list'))
        self.assertContains(response, 'Alpha Piano A')
        self.assertNotContains(response, 'Bravo Piano B')


class InvitationFlowTests(CompanyScopedTestCase):
    def setUp(self):
        self.company_name = 'Invite Co'
        self.company_slug = 'invite-co'
        super().setUp()
        self.admin = self.create_user(
            'inviteadmin',
            email='admin@example.com',
            role_admin=True,
            role_technician=True,
        )
        self.login_user(self.admin)

    def test_admin_can_send_company_invitation(self):
        response = self.client.post(reverse('settings'), {
            'action': 'invite',
            'invite-email': 'newtech@example.com',
            'invite-first_name': 'New',
            'invite-last_name': 'Tech',
            'invite-role_admin': '',
            'invite-role_technician': 'on',
        })

        self.assertRedirects(response, reverse('settings'))
        invitation = CompanyInvitation.objects.get(email='newtech@example.com')
        self.assertEqual(invitation.company, self.company)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(str(invitation.token), mail.outbox[0].body)

    def test_anonymous_user_can_accept_invitation_and_create_account(self):
        invitation = CompanyInvitation.objects.create(
            company=self.company,
            email='invitee@example.com',
            first_name='Invited',
            last_name='User',
            role_admin=False,
            role_technician=True,
            invited_by=self.admin,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.logout()

        response = self.client.post(
            reverse('company_invitation_accept', args=[invitation.token]),
            {
                'username': 'invitee',
                'first_name': 'Invited',
                'last_name': 'User',
                'email': 'invitee@example.com',
                'password1': 'StrongPass123',
                'password2': 'StrongPass123',
            },
        )

        self.assertRedirects(response, reverse('login'))
        user = Technician.objects.get(username='invitee')
        self.assertTrue(
            CompanyMembership.objects.filter(
                company=self.company,
                user=user,
                role_technician=True,
            ).exists()
        )
        self.assertFalse(user.role_admin)
        self.assertTrue(user.role_technician)

    def test_admin_can_revoke_pending_invitation(self):
        invitation = CompanyInvitation.objects.create(
            company=self.company,
            email='revoke@example.com',
            first_name='Revoke',
            last_name='Me',
            role_admin=False,
            role_technician=True,
            invited_by=self.admin,
            expires_at=timezone.now() + timedelta(days=7),
        )

        response = self.client.post(reverse('settings'), {
            'action': 'invite_revoke',
            'invitation_id': invitation.pk,
        })

        self.assertRedirects(response, reverse('settings'))
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, CompanyInvitation.Status.REVOKED)

    def test_admin_can_resend_pending_invitation(self):
        invitation = CompanyInvitation.objects.create(
            company=self.company,
            email='resend@example.com',
            first_name='Re',
            last_name='Send',
            role_admin=True,
            role_technician=True,
            invited_by=self.admin,
            expires_at=timezone.now() + timedelta(days=2),
        )
        old_token = invitation.token
        old_expiry = invitation.expires_at

        response = self.client.post(reverse('settings'), {
            'action': 'invite_resend',
            'invitation_id': invitation.pk,
        })

        self.assertRedirects(response, reverse('settings'))
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, CompanyInvitation.Status.PENDING)
        self.assertNotEqual(invitation.token, old_token)
        self.assertGreater(invitation.expires_at, old_expiry)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(str(invitation.token), mail.outbox[0].body)

    def test_settings_page_shows_invitation_history(self):
        CompanyInvitation.objects.create(
            company=self.company,
            email='accepted@example.com',
            first_name='Accepted',
            last_name='User',
            role_admin=False,
            role_technician=True,
            invited_by=self.admin,
            status=CompanyInvitation.Status.ACCEPTED,
            accepted_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=7),
        )
        CompanyInvitation.objects.create(
            company=self.company,
            email='revoked@example.com',
            first_name='Revoked',
            last_name='User',
            role_admin=False,
            role_technician=True,
            invited_by=self.admin,
            status=CompanyInvitation.Status.REVOKED,
            expires_at=timezone.now() + timedelta(days=7),
        )

        response = self.client.get(reverse('settings'))

        self.assertContains(response, 'Invitation History')
        self.assertContains(response, 'accepted@example.com')
        self.assertContains(response, 'revoked@example.com')


class CompanyRoleMethodTests(CompanyScopedTestCase):
    def test_membership_methods_are_company_aware(self):
        second_company = Company.objects.create(name='Second Co', slug='second-co')
        user = Technician.objects.create_user(
            username='companyroles',
            password='StrongPass123',
            role_admin=False,
            role_technician=False,
        )
        CompanyMembership.objects.create(
            company=self.company,
            user=user,
            role_admin=False,
            role_technician=True,
        )
        CompanyMembership.objects.create(
            company=second_company,
            user=user,
            role_admin=True,
            role_technician=True,
        )

        self.assertTrue(user.has_company_role(self.company, technician=True))
        self.assertFalse(user.has_company_role(self.company, admin=True))
        self.assertTrue(user.has_company_role(second_company, admin=True))
        self.assertTrue(user.can_be_assigned_in_company(self.company))
        self.assertFalse(user.can_be_assigned_in_company(Company.objects.create(name='No Access', slug='no-access')))


class PasswordResetTests(TestCase):
    def test_password_reset_sends_email(self):
        user = Technician.objects.create_user(
            username='resetuser',
            password='StrongPass123',
            email='reset@example.com',
        )
        company = Company.objects.create(name='Reset Co', slug='reset-co')
        CompanyMembership.objects.create(company=company, user=user, role_admin=False, role_technician=True, is_active=True)

        response = self.client.post(reverse('password_reset'), {
            'email': user.email,
        })

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('reset', mail.outbox[0].body.lower())


class BootstrapCompanyCommandTests(TestCase):
    def test_bootstrap_company_creates_company_admin_membership_and_settings(self):
        out = StringIO()

        call_command(
            'bootstrap_company',
            '--company-name', 'Bootstrap Co',
            '--admin-username', 'bootstrapadmin',
            '--admin-password', 'StrongPass123',
            '--admin-email', 'bootstrap@example.com',
            '--first-name', 'Boot',
            '--last-name', 'Strap',
            stdout=out,
        )

        company = Company.objects.get(slug='bootstrap-co')
        user = Technician.objects.get(username='bootstrapadmin')
        membership = CompanyMembership.objects.get(company=company, user=user)
        settings_obj = CompanySettings.objects.get(company=company)

        self.assertEqual(company.name, 'Bootstrap Co')
        self.assertEqual(user.email, 'bootstrap@example.com')
        self.assertTrue(membership.role_admin)
        self.assertTrue(membership.role_technician)
        self.assertEqual(settings_obj.company_name, 'Bootstrap Co')
        self.assertIn('Bootstrap complete', out.getvalue())


class ExpireInvitationsCommandTests(TestCase):
    def test_expire_invitations_marks_old_pending_invites_expired(self):
        company = Company.objects.create(name='Expire Co', slug='expire-co')
        invitation = CompanyInvitation.objects.create(
            company=company,
            email='old@example.com',
            expires_at=timezone.now() - timedelta(days=1),
        )
        out = StringIO()

        call_command('expire_invitations', stdout=out)

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, CompanyInvitation.Status.EXPIRED)
        self.assertIn('Expired 1 invitation', out.getvalue())


class SaaSReadinessReportCommandTests(TestCase):
    @override_settings(
        DEBUG=True,
        SECRET_KEY='dev-secret-key',
        ALLOWED_HOSTS=[],
        CSRF_TRUSTED_ORIGINS=[],
        DEFAULT_FROM_EMAIL='noreply@example.com',
        EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend',
        PRIVATE_MEDIA_URL_TTL=900,
        DEFAULT_FILE_STORAGE='django.core.files.storage.FileSystemStorage',
    )
    def test_report_flags_local_development_warnings(self):
        out = StringIO()

        call_command('saas_readiness_report', stdout=out)

        output = out.getvalue()
        self.assertIn('SaaS readiness report', output)
        self.assertIn('Warnings:', output)
        self.assertIn('console backend', output)
        self.assertIn('SQLite', output)
