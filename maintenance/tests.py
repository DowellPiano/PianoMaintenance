import os
import tempfile
from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from .models import MaintenanceSchedule, Photo, Piano, Technician, WorkOrder
from .services import generate_scheduled_work_orders


class SignupTests(TestCase):
    def test_public_signup_creates_inactive_technician_only_account(self):
        response = self.client.post(reverse('signup'), {
            'username': 'pendingtech',
            'first_name': 'Pending',
            'last_name': 'Tech',
            'email': 'pending@example.com',
            'password1': 'StrongPass123',
            'password2': 'StrongPass123',
        })

        self.assertRedirects(response, reverse('signup_pending'))
        user = Technician.objects.get(username='pendingtech')
        self.assertFalse(user.is_active)
        self.assertFalse(user.role_admin)
        self.assertTrue(user.role_technician)


class QRCodeRoutingTests(TestCase):
    def setUp(self):
        self.piano = Piano.objects.create(
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
        user = Technician.objects.create_user(
            username='qrtech',
            password='StrongPass123',
            role_admin=False,
            role_technician=True,
        )
        self.client.force_login(user)

        response = self.client.get(self.url)

        self.assertRedirects(response, reverse('piano_detail', args=[self.piano.pk]))


class PhotoDeletionTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root.name)
        self.settings_override.enable()
        self.piano = Piano.objects.create(
            name='Photo Piano',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
        )

    def tearDown(self):
        self.settings_override.disable()
        self.media_root.cleanup()

    def _create_photo(self, is_profile_photo=False):
        return Photo.objects.create(
            piano=self.piano,
            image=SimpleUploadedFile(
                'photo.jpg',
                b'test image content',
                content_type='image/jpeg',
            ),
            is_profile_photo=is_profile_photo,
        )

    def test_technician_can_delete_piano_photo(self):
        user = Technician.objects.create_user(
            username='phototech',
            password='StrongPass123',
            role_admin=False,
            role_technician=True,
        )
        photo = self._create_photo()
        image_path = photo.image.path
        self.client.force_login(user)

        response = self.client.post(reverse(
            'piano_photo_delete',
            args=[self.piano.pk, photo.pk],
        ))

        self.assertRedirects(response, reverse('piano_detail', args=[self.piano.pk]))
        self.assertFalse(Photo.objects.filter(pk=photo.pk).exists())
        self.assertFalse(os.path.exists(image_path))

    def test_admin_can_delete_piano_photo(self):
        user = Technician.objects.create_user(
            username='photoadmin',
            password='StrongPass123',
            role_admin=True,
            role_technician=False,
        )
        photo = self._create_photo()
        self.client.force_login(user)

        response = self.client.post(reverse(
            'piano_photo_delete',
            args=[self.piano.pk, photo.pk],
        ))

        self.assertRedirects(response, reverse('piano_detail', args=[self.piano.pk]))
        self.assertFalse(Photo.objects.filter(pk=photo.pk).exists())

    def test_deleting_profile_photo_promotes_next_photo(self):
        user = Technician.objects.create_user(
            username='profilephototech',
            password='StrongPass123',
            role_admin=False,
            role_technician=True,
        )
        profile_photo = self._create_photo(is_profile_photo=True)
        next_photo = self._create_photo()
        self.client.force_login(user)

        self.client.post(reverse(
            'piano_photo_delete',
            args=[self.piano.pk, profile_photo.pk],
        ))

        next_photo.refresh_from_db()
        self.assertTrue(next_photo.is_profile_photo)


class WorkOrderStateTests(TestCase):
    def setUp(self):
        self.tech = Technician.objects.create_user(
            username='state-tech',
            password='StrongPass123',
            first_name='State',
            last_name='Tech',
            role_admin=False,
            role_technician=True,
        )
        self.piano = Piano.objects.create(
            name='State Piano',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
        )
        self.client.force_login(self.tech)

    def test_workorder_list_uses_task_type_as_order_type(self):
        WorkOrder.objects.create(
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

    def test_piano_workorder_tab_links_to_workorder_detail(self):
        wo = WorkOrder.objects.create(
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

    def test_reopen_completed_workorder_clears_completed_date(self):
        wo = WorkOrder.objects.create(
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


class ScheduledWorkOrderGenerationTests(TestCase):
    def setUp(self):
        self.today = date(2026, 5, 12)
        self.piano = Piano.objects.create(
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


class ScheduleViewTests(TestCase):
    def setUp(self):
        self.tech = Technician.objects.create_user(
            username='scheduletech',
            password='StrongPass123',
            role_admin=False,
            role_technician=True,
        )
        self.piano = Piano.objects.create(
            name='Schedule Piano',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
        )
        self.client.force_login(self.tech)

    def _work_order(self, task_type, due_date=None):
        return WorkOrder.objects.create(
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


class TechnicianManagementTests(TestCase):
    def setUp(self):
        self.admin = Technician.objects.create_user(
            username='admin',
            password='StrongPass123',
            first_name='Admin',
            last_name='User',
            role_admin=True,
            role_technician=True,
        )
        self.client.force_login(self.admin)

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


class WorkOrderAssignmentTests(TestCase):
    def setUp(self):
        self.tech = Technician.objects.create_user(
            username='tech',
            password='StrongPass123',
            first_name='Test',
            last_name='Tech',
            role_admin=False,
            role_technician=True,
        )
        self.other_tech = Technician.objects.create_user(
            username='othertech',
            password='StrongPass123',
            first_name='Other',
            last_name='Tech',
            role_admin=False,
            role_technician=True,
        )
        self.client.force_login(self.tech)

    def test_technician_can_assign_self_to_unassigned_work_order(self):
        wo = WorkOrder.objects.create(
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
        tech = Technician.objects.create_user(
            username='dashboardtech',
            password='StrongPass123',
            role_admin=False,
            role_technician=True,
        )
        other_tech = Technician.objects.create_user(
            username='otherdashboardtech',
            password='StrongPass123',
            role_admin=False,
            role_technician=True,
        )
        assigned_open = WorkOrder.objects.create(
            assigned_tech=tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Assigned open',
        )
        assigned_in_progress = WorkOrder.objects.create(
            assigned_tech=tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.IN_PROGRESS,
            priority=WorkOrder.Priority.NORMAL,
            description='Assigned in progress',
        )
        WorkOrder.objects.create(
            assigned_tech=tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.COMPLETE,
            priority=WorkOrder.Priority.NORMAL,
            description='Assigned complete',
        )
        WorkOrder.objects.create(
            assigned_tech=other_tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Other tech open',
        )
        WorkOrder.objects.create(
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Unassigned open',
        )

        self.client.force_login(tech)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'My Work Orders')
        self.assertQuerySetEqual(
            response.context['dashboard_work_orders'],
            [assigned_in_progress, assigned_open],
            ordered=False,
        )


class WorkOrderListSortingTests(TestCase):
    def setUp(self):
        self.tech = Technician.objects.create_user(
            username='sorttech',
            password='StrongPass123',
            role_admin=False,
            role_technician=True,
        )
        self.client.force_login(self.tech)
        self.first_wo = WorkOrder.objects.create(
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='First work order',
        )
        self.second_wo = WorkOrder.objects.create(
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Second work order',
        )

    def test_work_order_list_sorts_by_clicked_column_and_direction(self):
        response = self.client.get(reverse('workorder_list'), {
            'sort': 'id',
            'dir': 'asc',
        })

        self.assertQuerySetEqual(
            response.context['work_orders'],
            [self.first_wo, self.second_wo],
        )

        response = self.client.get(reverse('workorder_list'), {
            'sort': 'id',
            'dir': 'desc',
        })

        self.assertQuerySetEqual(
            response.context['work_orders'],
            [self.second_wo, self.first_wo],
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
