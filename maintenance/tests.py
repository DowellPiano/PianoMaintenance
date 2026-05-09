import os
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from .models import Photo, Piano, Technician, WorkOrder


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
