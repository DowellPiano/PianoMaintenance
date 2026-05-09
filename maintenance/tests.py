from django.test import TestCase
from django.urls import reverse

from .models import Technician


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
