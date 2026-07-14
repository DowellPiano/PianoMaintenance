import os
import tempfile
from datetime import date, datetime, timedelta
from io import StringIO
from urllib.parse import urlencode
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.files.storage import Storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import (
    AuditLog,
    Company,
    CompanyInvitation,
    CompanyMembership,
    CompanySettings,
    ConditionReading,
    JobRun,
    MaintenanceLog,
    MaintenanceRequest,
    MaintenanceSchedule,
    Organization,
    Part,
    PartUsed,
    Photo,
    Piano,
    ScheduleTemplate,
    Tag,
    Technician,
    Venue,
    WorkOrder,
)
from .audit import log_audit_event
from .services import generate_scheduled_work_orders
from .views import _resolve_photo_storage_name
from piano_maintainer.monitoring import sanitize_sentry_event


class StubPhotoStorage(Storage):
    def __init__(self, names):
        self.names = set(names)

    def exists(self, name):
        return name in self.names

    def listdir(self, path):
        path = path.strip('/')
        prefix = f'{path}/' if path else ''
        child_dirs = set()
        child_files = set()

        for name in self.names:
            if prefix and not name.startswith(prefix):
                continue

            remaining = name[len(prefix):] if prefix else name
            if not remaining:
                continue

            if '/' in remaining:
                child_dirs.add(remaining.split('/', 1)[0])
            else:
                child_files.add(remaining)

        return sorted(child_dirs), sorted(child_files)


class PhotoStorageNameResolutionTests(TestCase):
    def test_uses_stored_name_when_it_exists(self):
        storage = StubPhotoStorage(['photos/26/06/12/photo.jpg'])

        resolved_name = _resolve_photo_storage_name(storage, 'photos/26/06/12/photo.jpg')

        self.assertEqual(resolved_name, 'photos/26/06/12/photo.jpg')

    def test_resolves_single_dated_photo_when_stored_name_is_missing_folders(self):
        storage = StubPhotoStorage(['photos/26/06/12/photo.jpg'])

        resolved_name = _resolve_photo_storage_name(storage, 'photos/photo.jpg')

        self.assertEqual(resolved_name, 'photos/26/06/12/photo.jpg')

    def test_resolves_expected_dated_photo_from_upload_timestamp(self):
        storage = StubPhotoStorage([
            'photos/26/06/12/photo.jpg',
            'photos/26/06/13/photo.jpg',
        ])

        resolved_name = _resolve_photo_storage_name(
            storage,
            'photos/photo.jpg',
            datetime(2026, 6, 13),
        )

        self.assertEqual(resolved_name, 'photos/26/06/13/photo.jpg')

    def test_keeps_stored_name_when_basename_matches_multiple_objects(self):
        storage = StubPhotoStorage([
            'photos/26/06/12/photo.jpg',
            'photos/26/06/13/photo.jpg',
        ])

        resolved_name = _resolve_photo_storage_name(storage, 'photos/photo.jpg')

        self.assertEqual(resolved_name, 'photos/photo.jpg')


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


class PerformanceRegressionTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.create_user(
            'performance-admin',
            role_admin=True,
            role_technician=True,
        )
        self.login_user(self.admin)

    def captured_get(self, url, data=None):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url, data or {})
        return response, queries.captured_queries

    def test_authenticated_request_reuses_memberships_without_rewriting_session(self):
        response, queries = self.captured_get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        membership_selects = [
            query['sql'] for query in queries
            if query['sql'].lstrip().upper().startswith('SELECT')
            and 'maintenance_companymembership' in query['sql']
        ]
        session_updates = [
            query['sql'] for query in queries
            if query['sql'].lstrip().upper().startswith('UPDATE')
            and 'django_session' in query['sql']
        ]
        self.assertEqual(len(membership_selects), 1)
        self.assertEqual(session_updates, [])

    def test_piano_list_query_count_is_fixed_and_results_are_paginated(self):
        Piano.objects.bulk_create([
            Piano(
                company=self.company,
                name=f'Performance Piano {index:02}',
                make='Yamaha',
                piano_type=Piano.PianoType.UPRIGHT,
            )
            for index in range(30)
        ])
        response, queries = self.captured_get(reverse('piano_list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].paginator.count, 30)
        self.assertEqual(len(response.context['pianos']), 25)
        photo_selects = [
            query['sql'] for query in queries
            if query['sql'].lstrip().upper().startswith('SELECT')
            and 'FROM "maintenance_photo"' in query['sql']
        ]
        self.assertEqual(len(photo_selects), 1)
        self.assertLessEqual(len(queries), 10)

        second_page = self.client.get(reverse('piano_list'), {'page': 2})
        self.assertEqual(len(second_page.context['pianos']), 5)

    def test_work_order_list_is_paginated_without_query_growth(self):
        WorkOrder.objects.bulk_create([
            WorkOrder(
                company=self.company,
                order_type=WorkOrder.OrderType.REQUEST,
                status=WorkOrder.Status.OPEN,
                priority=WorkOrder.Priority.NORMAL,
                description=f'Performance work order {index:02}',
            )
            for index in range(55)
        ])

        response, queries = self.captured_get(reverse('workorder_list'), {'page': 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].paginator.count, 55)
        self.assertEqual(len(response.context['work_orders']), 5)
        work_order_selects = [
            query['sql'] for query in queries
            if query['sql'].lstrip().upper().startswith('SELECT')
            and 'FROM "maintenance_workorder"' in query['sql']
        ]
        self.assertEqual(len(work_order_selects), 2)
        self.assertLessEqual(len(queries), 8)

    def test_dashboard_combines_work_order_counts(self):
        WorkOrder.objects.create(
            company=self.company,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )

        response, queries = self.captured_get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        work_order_selects = [
            query['sql'] for query in queries
            if query['sql'].lstrip().upper().startswith('SELECT')
            and 'FROM "maintenance_workorder"' in query['sql']
        ]
        self.assertEqual(len(work_order_selects), 2)
        self.assertLessEqual(len(queries), 12)

    def test_schedule_fetches_work_orders_once(self):
        task_types = ['Tuning', 'Regulation', 'Voicing', 'Cleaning']
        WorkOrder.objects.bulk_create([
            WorkOrder(
                company=self.company,
                order_type=WorkOrder.OrderType.PREVENTIVE,
                task_type=task_types[index % len(task_types)],
                status=WorkOrder.Status.OPEN,
                priority=WorkOrder.Priority.NORMAL,
            )
            for index in range(40)
        ])

        response, queries = self.captured_get(reverse('schedule'))

        self.assertEqual(response.status_code, 200)
        work_order_selects = [
            query['sql'] for query in queries
            if query['sql'].lstrip().upper().startswith('SELECT')
            and 'FROM "maintenance_workorder"' in query['sql']
        ]
        self.assertEqual(len(work_order_selects), 1)
        self.assertLessEqual(len(queries), 6)

    def test_platform_company_counts_use_correlated_subqueries(self):
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save(update_fields=['is_staff', 'is_superuser'])
        self.create_piano(name='Platform Performance Piano')
        WorkOrder.objects.create(
            company=self.company,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )

        response, queries = self.captured_get(reverse('platform_admin'))

        self.assertEqual(response.status_code, 200)
        company = next(
            item for item in response.context['companies']
            if item.pk == self.company.pk
        )
        self.assertEqual(company.active_member_count, 1)
        self.assertEqual(company.active_piano_count, 1)
        self.assertEqual(company.open_work_order_count, 1)
        company_summary_sql = next(
            query['sql'] for query in queries
            if 'active_member_count' in query['sql']
        )
        self.assertNotIn('LEFT OUTER JOIN "maintenance_workorder"', company_summary_sql)


class AuthEntryTests(TestCase):
    def test_login_page_does_not_offer_public_signup(self):
        response = self.client.get(reverse('login'))

        self.assertContains(response, 'Forgot your password?')
        self.assertContains(response, 'Contact your company admin or Overtone support.')
        self.assertNotContains(response, 'Request an account')


class HealthCheckTests(TestCase):
    def test_health_check_reports_ok_when_database_is_available(self):
        response = self.client.get(reverse('health_check'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    @patch('maintenance.views.connection.cursor', side_effect=RuntimeError('database unavailable'))
    def test_health_check_reports_unhealthy_without_leaking_error(self, mocked_cursor):
        response = self.client.get(reverse('health_check'))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unhealthy'})
        self.assertNotContains(
            response,
            'database unavailable',
            status_code=503,
        )

    def test_health_check_rejects_non_get_requests(self):
        response = self.client.post(reverse('health_check'))

        self.assertEqual(response.status_code, 405)


class DemoDataCommandTests(TestCase):
    @override_settings(DEBUG=False)
    def test_demo_data_command_refuses_to_run_outside_debug(self):
        with self.assertRaisesMessage(CommandError, 'must never run in production'):
            call_command('seed_demo_data')

        self.assertFalse(Company.objects.filter(slug='overtone-demo').exists())

    @override_settings(DEBUG=True, SENTRY_ENVIRONMENT='production')
    def test_demo_data_command_refuses_production_environment_even_with_debug(self):
        with self.assertRaisesMessage(CommandError, 'must never run in production'):
            call_command('seed_demo_data')

        self.assertFalse(Company.objects.filter(slug='overtone-demo').exists())

    @override_settings(DEBUG=True, SENTRY_ENVIRONMENT='development', SENTRY_RELEASE='render-sha')
    def test_demo_data_command_refuses_deployed_release(self):
        with self.assertRaisesMessage(CommandError, 'must never run in production'):
            call_command('seed_demo_data')

        self.assertFalse(Company.objects.filter(slug='overtone-demo').exists())

    @override_settings(DEBUG=True)
    def test_demo_data_command_is_idempotent(self):
        call_command('seed_demo_data', stdout=StringIO())
        call_command('seed_demo_data', stdout=StringIO())

        company = Company.objects.get(slug='overtone-demo')
        self.assertEqual(company.name, 'Overtone Demo Company')
        self.assertEqual(company.memberships.count(), 2)
        self.assertEqual(company.organizations.count(), 2)
        self.assertEqual(company.venues.count(), 3)
        self.assertEqual(company.pianos.count(), 5)
        self.assertEqual(company.parts.count(), 4)
        self.assertEqual(company.work_orders.count(), 4)
        self.assertEqual(company.maintenance_logs.count(), 1)
        self.assertEqual(company.condition_readings.count(), 1)
        self.assertEqual(company.invitations.filter(status='pending').count(), 1)

    @override_settings(DEBUG=True)
    def test_demo_data_reset_replaces_only_reserved_demo_records(self):
        real_company = Company.objects.create(name='Real Company', slug='real-company')
        call_command('seed_demo_data', stdout=StringIO())
        demo_company = Company.objects.get(slug='overtone-demo')
        Organization.objects.create(company=demo_company, name='Temporary Demo Record')

        call_command('seed_demo_data', reset=True, stdout=StringIO())

        self.assertTrue(Company.objects.filter(pk=real_company.pk).exists())
        reset_company = Company.objects.get(slug='overtone-demo')
        self.assertFalse(reset_company.organizations.filter(name='Temporary Demo Record').exists())
        self.assertEqual(reset_company.organizations.count(), 2)

    @override_settings(DEBUG=True)
    def test_demo_data_command_refuses_reserved_slug_collision(self):
        Company.objects.create(name='Real Customer', slug='overtone-demo')

        with self.assertRaisesMessage(CommandError, 'belongs to a different company'):
            call_command('seed_demo_data')

        self.assertEqual(Company.objects.get(slug='overtone-demo').name, 'Real Customer')


class SentrySanitizationTests(TestCase):
    def test_sanitizer_removes_sensitive_request_context(self):
        event = {
            'user': {'id': '42', 'email': 'customer@example.com'},
            'request': {
                'url': (
                    'https://app.example.com/invitations/'
                    '123e4567-e89b-42d3-a456-426614174000/accept/'
                ),
                'query_string': 'email=customer@example.com',
                'data': {'password': 'secret'},
                'cookies': {'sessionid': 'secret'},
                'headers': {
                    'Authorization': 'Bearer secret',
                    'Cookie': 'sessionid=secret',
                    'User-Agent': 'Browser',
                },
            },
        }

        sanitized = sanitize_sentry_event(event, {})

        self.assertNotIn('user', sanitized)
        request = sanitized['request']
        self.assertNotIn('query_string', request)
        self.assertNotIn('data', request)
        self.assertNotIn('cookies', request)
        self.assertNotIn('Authorization', request['headers'])
        self.assertNotIn('Cookie', request['headers'])
        self.assertEqual(request['headers']['User-Agent'], 'Browser')
        self.assertIn('<redacted-uuid>', request['url'])
        self.assertNotIn('123e4567-e89b-42d3-a456-426614174000', request['url'])


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='Overtone <app@example.com>',
)
class PlatformAdminTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        mail.outbox = []
        self.company_admin = self.create_user(
            'companyadmin',
            role_admin=True,
            role_technician=True,
        )
        self.superuser = self.create_user(
            'platformadmin',
            email='platform@example.com',
            role_admin=True,
            role_technician=True,
            is_staff=True,
            is_superuser=True,
        )

    def test_company_admin_cannot_access_platform_admin(self):
        self.login_user(self.company_admin)

        response = self.client.get(reverse('platform_admin'))

        self.assertEqual(response.status_code, 403)

    def test_company_admin_cannot_access_django_admin_even_if_staff(self):
        self.company_admin.is_staff = True
        self.company_admin.save(update_fields=['is_staff'])
        self.login_user(self.company_admin)

        response = self.client.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('admin:login'), response['Location'])

    def test_superuser_can_access_platform_admin(self):
        self.login_user(self.superuser)

        response = self.client.get(reverse('platform_admin'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Platform Admin')
        self.assertContains(response, 'Add Customer')
        self.assertContains(response, 'Memberships')
        self.assertContains(response, self.company_admin.username)
        self.assertContains(response, 'Remove Admin')

    def test_superuser_can_access_django_admin(self):
        self.login_user(self.superuser)

        response = self.client.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 200)

    def test_platform_admin_shows_recent_job_runs(self):
        JobRun.objects.create(
            job_name='generate_work_orders',
            status=JobRun.Status.SUCCESS,
            result={'created': 3},
            finished_at=timezone.now(),
        )
        self.login_user(self.superuser)

        response = self.client.get(reverse('platform_admin'))

        self.assertContains(response, 'Recent Job Runs')
        self.assertContains(response, 'generate_work_orders')
        self.assertContains(response, 'created')

    def test_superuser_can_create_company_and_send_admin_invitation(self):
        self.login_user(self.superuser)

        response = self.client.post(reverse('platform_admin'), {
            'action': 'create_company_invite',
            'company_name': 'Customer Co',
            'company_slug': 'customer-co',
            'admin_first_name': 'Casey',
            'admin_last_name': 'Customer',
            'admin_email': 'casey@example.com',
            'admin_is_technician': 'on',
        })

        self.assertRedirects(response, reverse('platform_admin'))
        company = Company.objects.get(slug='customer-co')
        settings_obj = CompanySettings.objects.get(company=company)
        invitation = CompanyInvitation.objects.get(company=company, email='casey@example.com')
        self.assertEqual(settings_obj.company_name, 'Customer Co')
        self.assertTrue(invitation.role_admin)
        self.assertTrue(invitation.role_technician)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('casey@example.com', mail.outbox[0].to)

    def test_create_company_rolls_back_if_invitation_email_fails(self):
        self.login_user(self.superuser)

        with self.settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='invalid.local'):
            response = self.client.post(reverse('platform_admin'), {
                'action': 'create_company_invite',
                'company_name': 'Rollback Co',
                'company_slug': 'rollback-co',
                'admin_email': 'rollback@example.com',
                'admin_is_technician': 'on',
            })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Customer was not created')
        self.assertFalse(Company.objects.filter(slug='rollback-co').exists())
        self.assertFalse(CompanyInvitation.objects.filter(email='rollback@example.com').exists())

    def test_superuser_can_resend_pending_invitation(self):
        self.login_user(self.superuser)
        invitation = CompanyInvitation.objects.create(
            company=self.company,
            email='pending@example.com',
            role_admin=True,
            role_technician=True,
            invited_by=self.superuser,
            expires_at=timezone.now() + timedelta(days=1),
        )
        original_token = invitation.token

        response = self.client.post(reverse('platform_admin'), {
            'action': 'resend_invitation',
            'invitation_id': invitation.pk,
        })

        self.assertRedirects(response, reverse('platform_admin'))
        invitation.refresh_from_db()
        self.assertNotEqual(invitation.token, original_token)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('pending@example.com', mail.outbox[0].to)

    def test_superuser_can_suspend_and_reactivate_company(self):
        self.login_user(self.superuser)

        response = self.client.post(reverse('platform_admin'), {
            'action': 'suspend_company',
            'company_id': self.company.pk,
        })

        self.assertRedirects(response, reverse('platform_admin'))
        self.company.refresh_from_db()
        self.assertFalse(self.company.is_active)
        self.assertTrue(AuditLog.objects.filter(
            company=self.company,
            event_type='platform.company_suspended',
        ).exists())

        self.client.post(reverse('platform_admin'), {
            'action': 'reactivate_company',
            'company_id': self.company.pk,
        })
        self.company.refresh_from_db()
        self.assertTrue(self.company.is_active)
        self.assertTrue(AuditLog.objects.filter(
            company=self.company,
            event_type='platform.company_reactivated',
        ).exists())

    def test_superuser_can_suspend_and_reactivate_non_admin_user(self):
        technician = self.create_user('supporttech')
        self.login_user(self.superuser)

        self.client.post(reverse('platform_admin'), {
            'action': 'suspend_user',
            'user_id': technician.pk,
        })

        technician.refresh_from_db()
        self.assertFalse(technician.is_active)
        self.assertTrue(AuditLog.objects.filter(
            company=self.company,
            event_type='platform.user_suspended',
            target_id=str(technician.pk),
        ).exists())

        self.client.post(reverse('platform_admin'), {
            'action': 'reactivate_user',
            'user_id': technician.pk,
        })
        technician.refresh_from_db()
        self.assertTrue(technician.is_active)

    def test_platform_console_does_not_suspend_superusers(self):
        self.login_user(self.superuser)

        self.client.post(reverse('platform_admin'), {
            'action': 'suspend_user',
            'user_id': self.superuser.pk,
        })

        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    def test_platform_console_refuses_to_suspend_a_companys_only_admin(self):
        orphaned_company = Company.objects.create(name='Only Admin Co', slug='only-admin-co')
        only_admin = self.create_user(
            'onlyadmin',
            company=orphaned_company,
            role_admin=True,
            role_technician=True,
        )
        self.login_user(self.superuser)

        response = self.client.post(reverse('platform_admin'), {
            'action': 'suspend_user',
            'user_id': only_admin.pk,
        }, follow=True)

        only_admin.refresh_from_db()
        self.assertTrue(only_admin.is_active)
        self.assertContains(response, 'Assign another active admin before disabling this user')

    def test_superuser_can_reassign_company_admin_role(self):
        replacement = self.create_user('replacementadmin')
        membership = CompanyMembership.objects.get(company=self.company, user=replacement)
        membership.is_active = False
        membership.save()
        self.login_user(self.superuser)

        self.client.post(reverse('platform_admin'), {
            'action': 'grant_company_admin',
            'membership_id': membership.pk,
        })

        membership.refresh_from_db()
        self.assertTrue(membership.is_active)
        self.assertTrue(membership.role_admin)
        self.assertTrue(AuditLog.objects.filter(
            company=self.company,
            event_type='platform.membership_admin_granted',
            target_id=str(replacement.pk),
        ).exists())

        self.client.post(reverse('platform_admin'), {
            'action': 'remove_company_admin',
            'membership_id': membership.pk,
        })
        membership.refresh_from_db()
        self.assertFalse(membership.role_admin)

    def test_platform_console_refuses_to_remove_last_active_admin(self):
        only_admin_company = Company.objects.create(name='Protected Co', slug='protected-co')
        only_admin = self.create_user(
            'protectedadmin',
            company=only_admin_company,
            role_admin=True,
        )
        membership = CompanyMembership.objects.get(company=only_admin_company, user=only_admin)
        self.login_user(self.superuser)

        response = self.client.post(reverse('platform_admin'), {
            'action': 'remove_company_admin',
            'membership_id': membership.pk,
        }, follow=True)

        membership.refresh_from_db()
        self.assertTrue(membership.role_admin)
        self.assertContains(response, 'Assign another active admin before removing this admin role')

    def test_superuser_can_revoke_pending_invitation(self):
        invitation = CompanyInvitation.objects.create(
            company=self.company,
            email='platform-revoke@example.com',
            invited_by=self.superuser,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.login_user(self.superuser)

        response = self.client.post(reverse('platform_admin'), {
            'action': 'revoke_invitation',
            'invitation_id': invitation.pk,
        })

        self.assertRedirects(response, reverse('platform_admin'))
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, CompanyInvitation.Status.REVOKED)


@override_settings(
    EMAIL_NOTIFICATIONS_ENABLED=True,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_HOST_USER='',
    EMAIL_HOST_PASSWORD='',
    DEFAULT_FROM_EMAIL='Overtone <app@example.com>',
)
class EmailNotificationTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        mail.outbox = []
        self.admin = self.create_user(
            'emailadmin',
            first_name='Email',
            last_name='Admin',
            email='admin@example.com',
            role_admin=True,
            role_technician=True,
        )

    def test_public_maintenance_request_emails_admins_and_requester(self):
        piano = self.create_piano(
            name='Email Request Piano',
            make='Yamaha',
        )

        response = self.client.post(reverse('maintenance-request-form', args=[piano.qr_code_token]), {
            'reported_by_name': 'Reporter',
            'reported_by_email': 'reporter@example.com',
            'issue_description': 'Sticky key',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'maintenance/maintenance_request_success.html')
        self.assertContains(response, 'Request received')
        self.assertContains(response, 'WO-')
        self.assertContains(response, 'Email Request Piano')
        self.assertContains(response, 'A confirmation email was sent to reporter@example.com')
        self.assertEqual(len(mail.outbox), 2)
        admin_email = mail.outbox[0]
        requester_email = mail.outbox[1]
        self.assertEqual(admin_email.to, ['admin@example.com'])
        self.assertEqual(admin_email.reply_to, ['reporter@example.com'])
        self.assertIn('New service request', admin_email.subject)
        self.assertIn('Sticky key', admin_email.body)
        self.assertIn(self.company.name, admin_email.body)
        self.assertEqual(requester_email.to, ['reporter@example.com'])
        self.assertEqual(requester_email.reply_to, ['admin@example.com'])
        self.assertIn('We received your service request', requester_email.subject)
        self.assertIn('Sticky key', requester_email.body)

    def test_public_maintenance_request_without_email_only_emails_admins(self):
        piano = self.create_piano(
            name='No Reporter Email Piano',
            make='Yamaha',
        )

        response = self.client.post(reverse('maintenance-request-form', args=[piano.qr_code_token]), {
            'reported_by_name': 'Reporter',
            'reported_by_email': '',
            'issue_description': 'Pedal squeak',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No email address was included')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['admin@example.com'])
        self.assertEqual(mail.outbox[0].reply_to, [])

    def test_workorder_assignment_emails_assigned_technician(self):
        tech = self.create_user(
            'assignedemailtech',
            first_name='Assigned',
            last_name='Tech',
            email='assigned@example.com',
        )
        self.login_user(self.admin)

        response = self.client.post(reverse('workorder_create'), {
            'piano': '',
            'order_type': WorkOrder.OrderType.REQUEST,
            'task_type': 'Other',
            'priority': WorkOrder.Priority.NORMAL,
            'assigned_tech': tech.pk,
            'description': 'Assigned work',
            'due_date': '',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['assigned@example.com'])
        self.assertIn('assigned to you', mail.outbox[0].subject)
        self.assertIn(self.company.name, mail.outbox[0].body)

    @override_settings(EMAIL_NOTIFICATIONS_ENABLED=False)
    def test_disabled_notifications_do_not_send_email(self):
        piano = self.create_piano(
            name='Notifications Disabled Piano',
            make='Yamaha',
        )

        response = self.client.post(reverse('maintenance-request-form', args=[piano.qr_code_token]), {
            'reported_by_name': 'Reporter',
            'reported_by_email': 'reporter@example.com',
            'issue_description': 'Sticky key',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)


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

    def test_user_from_other_company_cannot_discover_photo(self):
        other_company = Company.objects.create(name='Other Co', slug='other-co')
        outsider = self.create_user('outsider', company=other_company)
        photo = self._create_photo()
        self.login_user(outsider, company=other_company)

        response = self.client.get(reverse('photo_file', args=[photo.pk]))

        self.assertEqual(response.status_code, 404)

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
        work_order = WorkOrder.objects.get(
            piano=self.piano,
            task_type='Tuning',
            due_date=self.today - timedelta(days=1),
            status=WorkOrder.Status.OPEN,
        )
        self.assertFalse(work_order.is_team_job)

    def test_service_recalculates_built_in_due_from_latest_completed_work(self):
        self.piano.tuning_interval_value = 30
        self.piano.tuning_interval_unit = 'days'
        self.piano.next_tuning_due = self.today - timedelta(days=10)
        self.piano.save(update_fields=[
            'tuning_interval_value',
            'tuning_interval_unit',
            'next_tuning_due',
        ])
        WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Tuning',
            status=WorkOrder.Status.COMPLETE,
            priority=WorkOrder.Priority.NORMAL,
            due_date=self.today - timedelta(days=30),
            completed_date=self.today - timedelta(days=5),
        )

        generate_scheduled_work_orders(today=self.today)

        self.piano.refresh_from_db()
        self.assertEqual(self.piano.next_tuning_due, self.today + timedelta(days=25))
        self.assertFalse(WorkOrder.objects.filter(
            piano=self.piano,
            task_type='Tuning',
            status=WorkOrder.Status.OPEN,
            due_date=self.today - timedelta(days=10),
        ).exists())

    def test_service_creates_built_in_work_order_when_recalculated_due_is_past(self):
        self.piano.tuning_interval_value = 30
        self.piano.tuning_interval_unit = 'days'
        self.piano.next_tuning_due = self.today + timedelta(days=60)
        self.piano.save(update_fields=[
            'tuning_interval_value',
            'tuning_interval_unit',
            'next_tuning_due',
        ])
        WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type='Tuning',
            status=WorkOrder.Status.COMPLETE,
            priority=WorkOrder.Priority.NORMAL,
            due_date=self.today - timedelta(days=100),
            completed_date=self.today - timedelta(days=45),
        )

        result = generate_scheduled_work_orders(today=self.today)

        self.piano.refresh_from_db()
        recalculated_due = self.today - timedelta(days=15)
        self.assertEqual(self.piano.next_tuning_due, recalculated_due)
        self.assertGreaterEqual(result.created, 1)
        self.assertTrue(WorkOrder.objects.filter(
            piano=self.piano,
            task_type='Tuning',
            status=WorkOrder.Status.OPEN,
            due_date=recalculated_due,
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

        work_order = WorkOrder.objects.get(
            piano=self.piano,
            schedule=schedule,
            task_type='Inspection',
            due_date=self.today + timedelta(days=5),
        )
        self.assertFalse(work_order.is_team_job)

    def test_dry_run_does_not_create_work_orders(self):
        result = generate_scheduled_work_orders(today=self.today, dry_run=True)

        self.assertGreaterEqual(result.created, 1)
        self.assertFalse(WorkOrder.objects.filter(piano=self.piano).exists())

    def test_management_command_uses_generation_service(self):
        out = StringIO()

        call_command('generate_work_orders', '--dry-run', stdout=out)

        self.assertIn('DRY RUN', out.getvalue())
        self.assertIn('Done. Created:', out.getvalue())
        job_run = JobRun.objects.get(job_name='generate_work_orders')
        self.assertEqual(job_run.status, JobRun.Status.SUCCESS)
        self.assertTrue(job_run.metadata['dry_run'])
        self.assertIn('created', job_run.result)
        self.assertIsNotNone(job_run.finished_at)

    @patch(
        'maintenance.management.commands.generate_work_orders.generate_scheduled_work_orders',
        side_effect=RuntimeError('generation failed'),
    )
    def test_management_command_records_failure(self, mocked_generation):
        with self.assertRaisesMessage(RuntimeError, 'generation failed'):
            call_command('generate_work_orders')

        job_run = JobRun.objects.get(job_name='generate_work_orders')
        self.assertEqual(job_run.status, JobRun.Status.FAILED)
        self.assertIn('generation failed', job_run.error_message)
        self.assertIsNotNone(job_run.finished_at)

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

    def test_user_onboarding_is_invitation_only(self):
        response = self.client.get(reverse('technician_list'))

        self.assertContains(response, 'Invite User')
        self.assertContains(response, f'{reverse("settings")}#team-invitations')
        self.assertEqual(self.client.get('/technicians/new/').status_code, 404)

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

    def test_admin_cannot_assign_deactivated_technician(self):
        admin = self.create_user(
            'assignmentadmin',
            role_admin=True,
            role_technician=True,
        )
        membership = CompanyMembership.objects.get(
            company=self.company,
            user=self.other_tech,
        )
        membership.is_active = False
        membership.save()
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.create_piano(name='Inactive Assignment Piano'),
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )
        self.login_user(admin)

        response = self.client.post(reverse('workorder_assign', args=[wo.pk]), {
            'assigned_tech': self.other_tech.pk,
        })

        self.assertEqual(response.status_code, 200)
        wo.refresh_from_db()
        self.assertIsNone(wo.assigned_tech)

    def test_admin_can_edit_work_order_without_removing_historical_assignee(self):
        admin = self.create_user(
            'historicaladmin',
            role_admin=True,
            role_technician=True,
        )
        piano = self.create_piano(name='Historical Assignment Piano')
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=piano,
            assigned_tech=self.other_tech,
            order_type=WorkOrder.OrderType.REQUEST,
            task_type='Other',
            status=WorkOrder.Status.COMPLETE,
            priority=WorkOrder.Priority.NORMAL,
            description='Original description',
        )
        membership = CompanyMembership.objects.get(
            company=self.company,
            user=self.other_tech,
        )
        membership.is_active = False
        membership.save()
        self.login_user(admin)

        response = self.client.post(reverse('workorder_edit', args=[wo.pk]), {
            'piano': piano.pk,
            'order_type': WorkOrder.OrderType.REQUEST,
            'task_type': 'Other',
            'priority': WorkOrder.Priority.NORMAL,
            'assigned_tech': self.other_tech.pk,
            'description': 'Updated description',
            'due_date': '',
        })

        self.assertEqual(response.status_code, 302)
        wo.refresh_from_db()
        self.assertEqual(wo.assigned_tech, self.other_tech)
        self.assertEqual(wo.description, 'Updated description')


class WorkOrderTimerTemplateTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.tech = self.create_user(
            'timertech',
            first_name='Timer',
            last_name='Tech',
        )
        self.piano = self.create_piano(name='Timer Piano')
        self.work_order = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Timed work',
        )
        self.login_user(self.tech)

    def test_log_work_form_includes_client_side_timer(self):
        response = self.client.get(reverse('workorder_log_work', args=[self.work_order.pk]))

        self.assertContains(response, 'data-work-timer')
        self.assertContains(response, 'data-work-timer-start')
        self.assertContains(response, 'data-work-timer-end')
        self.assertContains(response, 'static/js/work-timer.js')
        self.assertContains(response, 'name="hours_worked" id="id_hours_worked"', html=False)
        self.assertContains(response, 'step="0.01"', html=False)

    def test_complete_form_includes_client_side_timer(self):
        response = self.client.get(reverse('workorder_complete', args=[self.work_order.pk]))

        self.assertContains(response, 'data-work-timer')
        self.assertContains(response, 'data-work-timer-start')
        self.assertContains(response, 'data-work-timer-end')
        self.assertContains(response, 'static/js/work-timer.js')
        self.assertContains(response, 'name="hours_worked" id="id_hours_worked"', html=False)
        self.assertContains(response, 'step="0.01"', html=False)


class TeamJobWorkOrderTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.create_user(
            'teamadmin',
            first_name='Team',
            last_name='Admin',
            role_admin=True,
            role_technician=True,
        )
        self.tech = self.create_user(
            'teamtech',
            first_name='Team',
            last_name='Tech',
        )
        self.other_tech = self.create_user(
            'teamlead',
            first_name='Team',
            last_name='Lead',
        )
        self.piano = self.create_piano(name='Team Piano')

    def _team_job(self, **kwargs):
        defaults = {
            'company': self.company,
            'piano': self.piano,
            'order_type': WorkOrder.OrderType.REQUEST,
            'status': WorkOrder.Status.OPEN,
            'priority': WorkOrder.Priority.NORMAL,
            'description': 'Shared work',
            'is_team_job': True,
        }
        defaults.update(kwargs)
        return WorkOrder.objects.create(**defaults)

    def test_work_orders_default_to_non_team_job(self):
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
        )

        self.assertFalse(wo.is_team_job)

    def test_create_and_edit_forms_save_team_job(self):
        self.login_user(self.admin)

        response = self.client.post(reverse('workorder_create'), {
            'piano': self.piano.pk,
            'order_type': WorkOrder.OrderType.REQUEST,
            'task_type': '',
            'priority': WorkOrder.Priority.NORMAL,
            'assigned_tech': self.other_tech.pk,
            'is_team_job': 'on',
            'description': 'Team-created work',
            'due_date': '',
        })

        self.assertEqual(response.status_code, 302)
        wo = WorkOrder.objects.get(description='Team-created work')
        self.assertTrue(wo.is_team_job)
        self.assertEqual(wo.assigned_tech, self.other_tech)

        response = self.client.post(reverse('workorder_edit', args=[wo.pk]), {
            'piano': self.piano.pk,
            'order_type': WorkOrder.OrderType.REQUEST,
            'task_type': '',
            'priority': WorkOrder.Priority.HIGH,
            'assigned_tech': '',
            'description': 'No longer team work',
            'due_date': '',
        })

        self.assertEqual(response.status_code, 302)
        wo.refresh_from_db()
        self.assertFalse(wo.is_team_job)
        self.assertIsNone(wo.assigned_tech)
        self.assertEqual(wo.priority, WorkOrder.Priority.HIGH)

    def test_team_jobs_are_visible_in_tech_mode_and_technician_dashboard(self):
        team_job = self._team_job(assigned_tech=self.other_tech, description='Visible team job')
        private_job = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.other_tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Other private job',
        )

        self.login_user(self.admin)
        session = self.client.session
        session['tech_mode'] = True
        session.save()

        response = self.client.get(reverse('workorder_list'))

        self.assertContains(response, f'WO-{team_job.pk}')
        self.assertNotContains(response, f'WO-{private_job.pk}')

        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, f'WO-{team_job.pk}')
        self.assertNotContains(response, f'WO-{private_job.pk}')

        self.login_user(self.tech)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, f'WO-{team_job.pk}')
        self.assertNotContains(response, f'WO-{private_job.pk}')

    def test_any_technician_can_log_work_on_team_job_without_changing_lead(self):
        wo = self._team_job(assigned_tech=self.other_tech)
        self.login_user(self.tech)

        response = self.client.post(reverse('workorder_log_work', args=[wo.pk]), {
            'hours_worked': '1.00',
            'work_performed': 'Worked with the team.',
            'notes': '',
        })

        self.assertEqual(response.status_code, 302)
        wo.refresh_from_db()
        log = wo.logs.get()
        self.assertEqual(wo.assigned_tech, self.other_tech)
        self.assertEqual(wo.status, WorkOrder.Status.IN_PROGRESS)
        self.assertEqual(log.technician, self.tech)

    def test_any_technician_can_complete_team_job_without_auto_assignment(self):
        wo = self._team_job()
        self.login_user(self.tech)

        response = self.client.post(reverse('workorder_complete', args=[wo.pk]), {
            'hours_worked': '1.25',
            'work_performed': 'Completed shared work.',
            'notes': '',
        })

        self.assertEqual(response.status_code, 302)
        wo.refresh_from_db()
        log = wo.logs.get()
        self.assertIsNone(wo.assigned_tech)
        self.assertEqual(wo.status, WorkOrder.Status.COMPLETE)
        self.assertEqual(log.technician, self.tech)

    def test_team_job_detail_shows_badge_actions_and_no_take_button(self):
        wo = self._team_job()
        self.login_user(self.tech)

        response = self.client.get(reverse('workorder_detail', args=[wo.pk]))

        self.assertContains(response, 'Team Job')
        self.assertContains(response, 'Log Work')
        self.assertContains(response, 'Mark Complete')
        self.assertNotContains(response, '>Take<', html=False)

    def test_technician_cannot_take_team_job(self):
        wo = self._team_job()
        self.login_user(self.tech)

        response = self.client.post(reverse('workorder_assign', args=[wo.pk]), {
            'assign_action': 'assign_self',
        })

        self.assertEqual(response.status_code, 200)
        wo.refresh_from_db()
        self.assertIsNone(wo.assigned_tech)

    def test_team_job_badge_shows_on_piano_work_order_tab(self):
        wo = self._team_job()
        self.login_user(self.tech)

        response = self.client.get(reverse('piano_tab', args=[self.piano.pk, 'work-orders']))

        self.assertContains(response, f'WO-{wo.pk}')
        self.assertContains(response, 'Team Job')


class WorkOrderListAssignmentTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.create_user(
            'assignadmin',
            first_name='Assign',
            last_name='Admin',
            role_admin=True,
            role_technician=True,
        )
        self.tech = self.create_user(
            'assigntech',
            first_name='Assign',
            last_name='Tech',
        )
        self.login_user(self.admin)

    def test_workorder_list_assignment_dropdown_includes_company_technicians(self):
        WorkOrder.objects.create(
            company=self.company,
            piano=self.create_piano(name='Dropdown Piano'),
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Needs assignment',
        )

        response = self.client.get(reverse('workorder_list'))

        self.assertContains(response, '<select name="assigned_tech"', html=False)
        self.assertContains(response, f'value="{self.admin.pk}"')
        self.assertContains(response, 'Assign Admin')
        self.assertContains(response, f'value="{self.tech.pk}"')
        self.assertContains(response, 'Assign Tech')


class TechnicianModeTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        self.admin_tech = self.create_user(
            'admintech',
            first_name='Admin',
            last_name='Tech',
            role_admin=True,
            role_technician=True,
        )
        self.other_tech = self.create_user(
            'othermodetech',
            first_name='Other',
            last_name='Tech',
        )
        self.login_user(self.admin_tech)

    def _enable_tech_mode(self):
        session = self.client.session
        session['tech_mode'] = True
        session.save()

    def test_dual_role_user_can_toggle_tech_mode(self):
        response = self.client.post(reverse('toggle_tech_mode'), {
            'tech_mode': 'on',
            'return_url': reverse('dashboard'),
        })

        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(self.client.session['tech_mode'])

    def test_tech_mode_uses_technician_dashboard(self):
        self._enable_tech_mode()
        mine = WorkOrder.objects.create(
            company=self.company,
            piano=self.create_piano(name='Mine Piano'),
            assigned_tech=self.admin_tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Mine',
        )
        theirs = WorkOrder.objects.create(
            company=self.company,
            piano=self.create_piano(name='Their Piano'),
            assigned_tech=self.other_tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Theirs',
        )

        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'My Work')
        self.assertContains(response, 'My Work Orders')
        self.assertContains(response, f'WO-{mine.pk}')
        self.assertNotContains(response, f'WO-{theirs.pk}')
        self.assertNotContains(response, 'Pending Requests')

    def test_tech_mode_hides_admin_navigation(self):
        self._enable_tech_mode()

        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'mode-switch mode-switch-tech')
        self.assertContains(response, '<span class="mode-label active">Tech</span>', html=True)
        self.assertContains(response, '<span class="mode-label">Admin</span>', html=True)
        self.assertNotContains(response, f'href="{reverse("technician_list")}"')
        self.assertNotContains(response, f'href="{reverse("reports")}"')

    def test_tech_mode_admin_can_take_unassigned_work_order(self):
        self._enable_tech_mode()
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.create_piano(name='Available Piano'),
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description='Available',
        )

        detail_response = self.client.get(reverse('workorder_detail', args=[wo.pk]))
        self.assertContains(detail_response, 'Take')
        self.assertNotContains(detail_response, '<select name="assigned_tech"')

        response = self.client.post(reverse('workorder_assign', args=[wo.pk]), {
            'assign_action': 'assign_self',
        })

        self.assertEqual(response.status_code, 200)
        wo.refresh_from_db()
        self.assertEqual(wo.assigned_tech, self.admin_tech)
        self.assertEqual(wo.status, WorkOrder.Status.IN_PROGRESS)

    def test_tech_mode_admin_cannot_edit_other_technicians_work_order(self):
        self._enable_tech_mode()
        wo = WorkOrder.objects.create(
            company=self.company,
            piano=self.create_piano(name='Busy Piano'),
            assigned_tech=self.other_tech,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.IN_PROGRESS,
            priority=WorkOrder.Priority.NORMAL,
            description='Already assigned',
        )

        response = self.client.get(reverse('workorder_detail', args=[wo.pk]))

        self.assertNotContains(response, reverse('workorder_edit', args=[wo.pk]))
        self.assertNotContains(response, reverse('workorder_delete', args=[wo.pk]))
        self.assertNotContains(response, 'Mark Complete')


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

    def test_switch_company_rejects_external_redirect(self):
        response = self.client.post(reverse('switch_company'), {
            'company_id': self.company_b.pk,
            'next': 'https://attacker.example/collect',
        })

        self.assertRedirects(response, reverse('dashboard'))
        session = self.client.session
        self.assertEqual(session['active_company_id'], self.company_b.pk)


class IdentityEmailTests(CompanyScopedTestCase):
    def test_user_email_is_normalized_and_case_insensitively_unique(self):
        user = self.create_user('normalized', email='  DowellPiano@Gmail.com ')

        user.refresh_from_db()
        self.assertEqual(user.email, 'dowellpiano@gmail.com')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Technician.objects.create_user(
                username='duplicate-email',
                password='StrongPass123',
                email='DOWELLPIANO@gmail.com',
            )

    def test_pending_invitation_email_is_normalized_and_case_insensitively_unique(self):
        CompanyInvitation.objects.create(
            company=self.company,
            email='  NewTech@Example.com ',
            expires_at=timezone.now() + timedelta(days=7),
        )

        invitation = CompanyInvitation.objects.get(company=self.company)
        self.assertEqual(invitation.email, 'newtech@example.com')
        with self.assertRaises(IntegrityError), transaction.atomic():
            CompanyInvitation.objects.create(
                company=self.company,
                email='NEWTECH@example.com',
                expires_at=timezone.now() + timedelta(days=7),
            )


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

    def test_admin_gets_friendly_error_for_duplicate_pending_invitation(self):
        CompanyInvitation.objects.create(
            company=self.company,
            email='pending@example.com',
            invited_by=self.admin,
            expires_at=timezone.now() + timedelta(days=7),
        )
        mail.outbox = []

        response = self.client.post(reverse('settings'), {
            'action': 'invite',
            'invite-email': 'PENDING@example.com',
            'invite-first_name': 'Pending',
            'invite-last_name': 'User',
            'invite-role_technician': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A pending invitation already exists for this email address.')
        self.assertEqual(CompanyInvitation.objects.filter(company=self.company).count(), 1)
        self.assertEqual(len(mail.outbox), 0)

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

    def test_authenticated_invitation_email_match_is_case_insensitive(self):
        other_company = Company.objects.create(name='Existing Co', slug='existing-co')
        user = self.create_user(
            'existinginvitee',
            company=other_company,
            email='DowellPiano@gmail.com',
        )
        invitation = CompanyInvitation.objects.create(
            company=self.company,
            email='dowellpiano@gmail.com',
            role_admin=False,
            role_technician=True,
            invited_by=self.admin,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.login_user(user, company=other_company)

        response = self.client.get(
            reverse('company_invitation_accept', args=[invitation.token])
        )

        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(CompanyMembership.objects.filter(
            company=self.company,
            user=user,
            role_technician=True,
            is_active=True,
        ).exists())

    def test_anonymous_existing_user_is_sent_to_login_then_back_to_invitation(self):
        existing_company = Company.objects.create(name='Existing User Co', slug='existing-user-co')
        self.create_user(
            'existing-account',
            company=existing_company,
            email='existing@example.com',
        )
        invitation = CompanyInvitation.objects.create(
            company=self.company,
            email='EXISTING@example.com',
            role_technician=True,
            invited_by=self.admin,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.logout()

        response = self.client.get(reverse('company_invitation_accept', args=[invitation.token]))

        expected_next = reverse('company_invitation_accept', args=[invitation.token])
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('login')))
        self.assertIn(urlencode({'next': expected_next}), response.url)

    def test_anonymous_signup_must_use_invited_email(self):
        invitation = CompanyInvitation.objects.create(
            company=self.company,
            email='correct@example.com',
            role_technician=True,
            invited_by=self.admin,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.logout()

        response = self.client.post(
            reverse('company_invitation_accept', args=[invitation.token]),
            {
                'username': 'wrong-email',
                'first_name': 'Wrong',
                'last_name': 'Email',
                'email': 'different@example.com',
                'password1': 'StrongPass123',
                'password2': 'StrongPass123',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Use the email address that received this invitation.')
        self.assertFalse(Technician.objects.filter(username='wrong-email').exists())

    def test_authenticated_user_with_blank_email_cannot_accept_invitation(self):
        other_company = Company.objects.create(name='Blank Email Co', slug='blank-email-co')
        user = self.create_user('blankemailinvitee', company=other_company, email='')
        invitation = CompanyInvitation.objects.create(
            company=self.company,
            email='invitee@example.com',
            role_admin=False,
            role_technician=True,
            invited_by=self.admin,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.login_user(user, company=other_company)

        response = self.client.get(
            reverse('company_invitation_accept', args=[invitation.token])
        )

        self.assertRedirects(response, reverse('settings'))
        self.assertFalse(CompanyMembership.objects.filter(
            company=self.company,
            user=user,
        ).exists())
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, CompanyInvitation.Status.PENDING)

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


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='Overtone <app@example.com>',
)
class PasswordResetTests(TestCase):
    def setUp(self):
        mail.outbox = []
        self.user = Technician.objects.create_user(
            username='resetuser',
            password='OldStrongPass123',
            email='reset@example.com',
            is_active=True,
        )
        company = Company.objects.create(name='Reset Co', slug='reset-co')
        CompanyMembership.objects.create(company=company, user=self.user, role_admin=False, role_technician=True, is_active=True)

    def test_password_reset_sends_email_for_active_user(self):
        response = self.client.post(reverse('password_reset'), {
            'email': self.user.email,
        })

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['reset@example.com'])
        self.assertIn('Reset your Overtone password', mail.outbox[0].subject)
        self.assertIn('/password-reset/', mail.outbox[0].body)

    def test_password_reset_confirm_updates_password(self):
        self.client.post(reverse('password_reset'), {
            'email': self.user.email,
        })
        reset_url = mail.outbox[0].body.split('Use this link to choose a new password:\n', 1)[1].splitlines()[0]
        path = '/' + reset_url.split('/', 3)[3]
        response = self.client.get(path)

        self.assertEqual(response.status_code, 302)
        set_password_path = response['Location']
        response = self.client.post(set_password_path, {
            'new_password1': 'NewStrongPass123',
            'new_password2': 'NewStrongPass123',
        })

        self.assertRedirects(response, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewStrongPass123'))


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
        self.assertFalse(user.is_staff)
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
        job_run = JobRun.objects.get(job_name='expire_invitations')
        self.assertEqual(job_run.status, JobRun.Status.SUCCESS)
        self.assertEqual(job_run.result, {'expired': 1})


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

    @override_settings(
        DEBUG=False,
        SECRET_KEY='production-shaped-secret-key',
        ALLOWED_HOSTS=['app.example.com'],
        CSRF_TRUSTED_ORIGINS=['https://app.example.com'],
        DEFAULT_FROM_EMAIL='noreply@example.com',
        PRIVATE_MEDIA_URL_TTL=900,
    )
    def test_report_flags_non_superuser_staff_accounts(self):
        Technician.objects.create_user(
            username='legacy-staff',
            password='StrongPass123',
            is_staff=True,
            is_superuser=False,
        )
        out = StringIO()

        call_command('saas_readiness_report', stdout=out)

        self.assertIn('non-superuser staff account', out.getvalue())


class TenantRelationshipValidationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Tenant A', slug='tenant-a')
        self.other_company = Company.objects.create(name='Tenant B', slug='tenant-b')
        self.technician = Technician.objects.create_user(
            username='tenant-tech',
            password='StrongPass123',
        )
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.technician,
            role_admin=False,
            role_technician=True,
            is_active=True,
        )
        self.piano = Piano.objects.create(
            company=self.company,
            name='Tenant Piano',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
        )
        self.other_piano = Piano.objects.create(
            company=self.other_company,
            name='Other Piano',
            make='Steinway',
            piano_type=Piano.PianoType.GRAND,
        )

    def test_location_and_tag_relationships_reject_other_company(self):
        other_organization = Organization.objects.create(
            company=self.other_company,
            name='Other Organization',
        )
        other_venue = Venue.objects.create(
            company=self.other_company,
            name='Other Venue',
        )
        other_tag = Tag.objects.create(company=self.other_company, name='Other Tag')

        with self.assertRaises(ValidationError):
            Venue.objects.create(
                company=self.company,
                organization=other_organization,
                name='Invalid Venue',
            )
        with self.assertRaises(ValidationError):
            Piano.objects.create(
                company=self.company,
                venue=other_venue,
                name='Invalid Piano',
                make='Yamaha',
                piano_type=Piano.PianoType.UPRIGHT,
            )
        with self.assertRaises(ValidationError):
            self.piano.tags.add(other_tag)

    def test_schedule_relationships_reject_other_company(self):
        other_template = ScheduleTemplate.objects.create(
            company=self.other_company,
            name='Other Template',
            task_name='Other Task',
            task_type='Other',
            interval_days=30,
        )

        with self.assertRaises(ValidationError):
            MaintenanceSchedule.objects.create(
                company=self.company,
                piano=self.other_piano,
                task_name='Invalid Piano Schedule',
                task_type='Other',
                interval_days=30,
            )
        with self.assertRaises(ValidationError):
            MaintenanceSchedule.objects.create(
                company=self.company,
                piano=self.piano,
                template=other_template,
                task_name='Invalid Template Schedule',
                task_type='Other',
                interval_days=30,
            )

    def test_work_order_rejects_cross_company_links(self):
        other_schedule = MaintenanceSchedule.objects.create(
            company=self.other_company,
            piano=self.other_piano,
            task_name='Other Schedule',
            task_type='Other',
            interval_days=30,
        )

        with self.assertRaises(ValidationError):
            WorkOrder.objects.create(
                company=self.company,
                piano=self.other_piano,
                order_type=WorkOrder.OrderType.REQUEST,
            )
        with self.assertRaises(ValidationError):
            WorkOrder.objects.create(
                company=self.company,
                piano=self.piano,
                schedule=other_schedule,
                order_type=WorkOrder.OrderType.PREVENTIVE,
            )

    def test_deactivated_technician_cannot_receive_new_assignment(self):
        self.membership.is_active = False
        self.membership.save()

        with self.assertRaises(ValidationError):
            WorkOrder.objects.create(
                company=self.company,
                piano=self.piano,
                assigned_tech=self.technician,
                order_type=WorkOrder.OrderType.REQUEST,
            )

    def test_deactivated_technician_remains_on_existing_work_order(self):
        work_order = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.technician,
            order_type=WorkOrder.OrderType.REQUEST,
        )
        self.membership.is_active = False
        self.membership.save()

        work_order.description = 'Historical edit'
        work_order.save(update_fields=['description'])

        work_order.refresh_from_db()
        self.assertEqual(work_order.assigned_tech, self.technician)
        self.assertEqual(work_order.description, 'Historical edit')

    def test_logs_preserve_history_but_reject_new_inactive_technician(self):
        work_order = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.technician,
            order_type=WorkOrder.OrderType.REQUEST,
        )
        log = MaintenanceLog.objects.create(
            company=self.company,
            work_order=work_order,
            technician=self.technician,
            piano=self.piano,
            hours_worked=1,
            work_performed='Initial work',
        )
        self.membership.is_active = False
        self.membership.save()

        log.notes = 'Historical note'
        log.save(update_fields=['notes'])
        self.assertEqual(log.technician, self.technician)

        with self.assertRaises(ValidationError):
            MaintenanceLog.objects.create(
                company=self.company,
                work_order=work_order,
                technician=self.technician,
                piano=self.piano,
                hours_worked=1,
                work_performed='Invalid new work',
            )

    def test_log_reading_part_and_request_relationships_are_validated(self):
        work_order = WorkOrder.objects.create(
            company=self.company,
            piano=self.piano,
            assigned_tech=self.technician,
            order_type=WorkOrder.OrderType.REQUEST,
        )
        log = MaintenanceLog.objects.create(
            company=self.company,
            work_order=work_order,
            technician=self.technician,
            piano=self.piano,
            hours_worked=1,
            work_performed='Work',
        )
        other_part = Part.objects.create(company=self.other_company, name='Other Part')

        with self.assertRaises(ValidationError):
            MaintenanceLog.objects.create(
                company=self.company,
                work_order=work_order,
                technician=self.technician,
                piano=self.other_piano,
                hours_worked=1,
                work_performed='Invalid work',
            )
        with self.assertRaises(ValidationError):
            ConditionReading.objects.create(
                company=self.company,
                piano=self.other_piano,
                log=log,
            )
        with self.assertRaises(ValidationError):
            PartUsed.objects.create(
                company=self.company,
                log=log,
                part=other_part,
                quantity_used=1,
            )
        with self.assertRaises(ValidationError):
            MaintenanceRequest.objects.create(
                company=self.company,
                piano=self.other_piano,
                work_order=work_order,
                issue_description='Invalid request',
            )


class TenantIntegrityCommandTests(TestCase):
    def test_command_passes_for_consistent_relationships(self):
        company = Company.objects.create(name='Integrity Co', slug='integrity-co')
        organization = Organization.objects.create(company=company, name='Integrity Org')
        venue = Venue.objects.create(
            company=company,
            organization=organization,
            name='Integrity Venue',
        )
        Piano.objects.create(
            company=company,
            venue=venue,
            name='Integrity Piano',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
        )
        out = StringIO()

        call_command('check_tenant_integrity', stdout=out)

        self.assertIn('All tenant integrity checks passed.', out.getvalue())

    def test_command_fails_for_cross_company_relationship(self):
        company = Company.objects.create(name='Integrity A', slug='integrity-a')
        other_company = Company.objects.create(name='Integrity B', slug='integrity-b')
        other_venue = Venue.objects.create(company=other_company, name='Other Venue')
        piano = Piano.objects.create(
            company=company,
            name='Mismatched Piano',
            make='Yamaha',
            piano_type=Piano.PianoType.UPRIGHT,
        )
        Piano.objects.filter(pk=piano.pk).update(venue=other_venue)
        out = StringIO()

        with self.assertRaisesMessage(CommandError, '1 violation(s)'):
            call_command('check_tenant_integrity', stdout=out)

        self.assertIn('[FAIL] piano.venue_company: 1', out.getvalue())
