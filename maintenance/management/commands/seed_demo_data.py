from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from maintenance.models import (
    Company,
    CompanyInvitation,
    CompanyMembership,
    CompanySettings,
    ConditionLevel,
    ConditionReading,
    MaintenanceLog,
    MaintenanceSchedule,
    Organization,
    Part,
    PartUsed,
    Piano,
    TaskType,
    Technician,
    Venue,
    WorkOrder,
)


DEMO_COMPANY_NAME = 'Overtone Demo Company'
DEMO_COMPANY_SLUG = 'overtone-demo'
DEMO_USERS = {
    'demo_admin': {
        'email': 'admin@overtone-demo.invalid',
        'first_name': 'Alex',
        'last_name': 'Admin',
        'role_admin': True,
        'role_technician': True,
    },
    'demo_technician': {
        'email': 'technician@overtone-demo.invalid',
        'first_name': 'Taylor',
        'last_name': 'Technician',
        'role_admin': False,
        'role_technician': True,
    },
}


class Command(BaseCommand):
    help = 'Create or reset deterministic fictional demo data in an undeployed DEBUG environment.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete and recreate only the reserved Overtone demo company and users.',
        )
        parser.add_argument(
            '--password',
            default='OvertoneDemo123!',
            help='Password assigned to both local demo accounts.',
        )

    def handle(self, *args, **options):
        is_deployed_environment = bool(getattr(settings, 'SENTRY_RELEASE', ''))
        is_production_environment = (
            getattr(settings, 'SENTRY_ENVIRONMENT', '').strip().casefold() == 'production'
        )
        if not settings.DEBUG or is_deployed_environment or is_production_environment:
            raise CommandError(
                'Demo data requires an undeployed DEBUG environment and must never run in production.'
            )

        password = options['password']
        if len(password) < 8:
            raise CommandError('Demo password must be at least 8 characters.')

        with transaction.atomic():
            company = Company.objects.filter(slug=DEMO_COMPANY_SLUG).first()
            self._validate_reserved_records(company)
            if options['reset']:
                self._reset(company)
            company = self._seed(password)

        self.stdout.write(self.style.SUCCESS(
            'Demo data ready for {company}. Users: {users}.'.format(
                company=company.name,
                users=', '.join(DEMO_USERS),
            )
        ))

    def _validate_reserved_records(self, company):
        if company and company.name != DEMO_COMPANY_NAME:
            raise CommandError(
                f'The reserved slug {DEMO_COMPANY_SLUG!r} belongs to a different company; refusing to modify it.'
            )

        for username, spec in DEMO_USERS.items():
            email_owner = Technician.objects.filter(email__iexact=spec['email']).exclude(
                username=username,
            ).first()
            if email_owner:
                raise CommandError(
                    f'Reserved demo email {spec["email"]!r} belongs to a different account.'
                )
            user = Technician.objects.filter(username=username).first()
            if not user:
                continue
            if (user.email or '').strip().casefold() != spec['email']:
                raise CommandError(f'Reserved demo username {username!r} belongs to a different account.')
            other_memberships = user.company_memberships.all()
            if company:
                other_memberships = other_memberships.exclude(company=company)
            if other_memberships.exists():
                raise CommandError(f'Demo user {username!r} has a non-demo membership; refusing to modify it.')

    def _reset(self, company):
        if company:
            # PartUsed protects its Part while both are otherwise company-owned.
            # Remove usages first so Django can collect the remaining demo graph.
            PartUsed.objects.filter(company=company).delete()
            company.delete()
        for username in DEMO_USERS:
            user = Technician.objects.filter(username=username).first()
            if user and not user.company_memberships.exists():
                user.delete()

    def _seed(self, password):
        company, _ = Company.objects.update_or_create(
            slug=DEMO_COMPANY_SLUG,
            defaults={'name': DEMO_COMPANY_NAME, 'is_active': True},
        )
        company_settings = CompanySettings.load_for_company(company)
        company_settings.company_name = company.name
        company_settings.address = '1000 Harmony Avenue\nExample City, IL 60000'
        company_settings.phone = '555-0100'
        company_settings.email = 'office@overtone-demo.invalid'
        company_settings.default_labor_rate = Decimal('125.00')
        company_settings.save()

        users = {}
        for username, spec in DEMO_USERS.items():
            user, _ = Technician.objects.get_or_create(username=username)
            user.email = spec['email']
            user.first_name = spec['first_name']
            user.last_name = spec['last_name']
            user.is_active = True
            user.is_staff = False
            user.is_superuser = False
            user.set_password(password)
            user.save()
            CompanyMembership.objects.update_or_create(
                company=company,
                user=user,
                defaults={
                    'role_admin': spec['role_admin'],
                    'role_technician': spec['role_technician'],
                    'is_active': True,
                },
            )
            users[username] = user

        academy, _ = Organization.objects.update_or_create(
            company=company,
            name='Lakeside Arts Academy',
            defaults={
                'short_name': 'Lakeside',
                'contact_name': 'Jordan Lee',
                'contact_email': 'jordan@lakeside-demo.invalid',
                'notes': 'Fictional education customer used for demonstrations.',
            },
        )
        symphony, _ = Organization.objects.update_or_create(
            company=company,
            name='Example City Symphony',
            defaults={
                'short_name': 'ECS',
                'contact_name': 'Morgan Rivera',
                'contact_email': 'morgan@symphony-demo.invalid',
            },
        )

        recital_hall = self._venue(company, academy, 'Lakeside Recital Hall', '100 Music Lane')
        practice_center = self._venue(company, academy, 'Lakeside Practice Center', '110 Music Lane')
        concert_hall = self._venue(company, symphony, 'Example Concert Hall', '200 Symphony Way')

        concert_grand = self._piano(
            company, concert_hall, 'Concert Grand', 'Steinway & Sons', Piano.PianoType.GRAND,
            model='D-274', serial_number='DEMO-D-001', room='Main Stage', year_built=2018,
        )
        recital_grand = self._piano(
            company, recital_hall, 'Recital Grand', 'Yamaha', Piano.PianoType.GRAND,
            model='C7X', serial_number='DEMO-C7X-001', room='Stage', year_built=2020,
        )
        studio_upright = self._piano(
            company, practice_center, 'Studio Upright 101', 'Yamaha', Piano.PianoType.UPRIGHT,
            model='U3', serial_number='DEMO-U3-101', room='101', year_built=2016,
        )
        self._piano(
            company, practice_center, 'Studio Upright 102', 'Kawai', Piano.PianoType.UPRIGHT,
            model='K-500', serial_number='DEMO-K500-102', room='102', year_built=2019,
        )
        self._piano(
            company, recital_hall, 'Rehearsal Digital', 'Yamaha', Piano.PianoType.DIGITAL,
            model='NU1X', serial_number='DEMO-NU1X-001', room='Green Room', year_built=2021,
        )

        MaintenanceSchedule.objects.update_or_create(
            company=company,
            piano=concert_grand,
            task_name='Quarterly concert tuning',
            defaults={
                'task_type': TaskType.TUNING,
                'interval_days': 90,
                'warning_days_before': 14,
                'is_active': True,
                'last_service_date': timezone.localdate() - timedelta(days=80),
            },
        )

        tuning_pin = self._part(company, 'Tuning Pin', 'TP-2/0', '3.25', 48, 20)
        caster = self._part(company, 'Grand Piano Caster', 'GPC-100', '42.50', 2, 2)
        self._part(company, 'Hammer Felt Strip', 'HF-10', '18.75', 8, 3)
        self._part(company, 'Key Bushing Cloth', 'KBC-5', '12.00', 1, 2)

        today = timezone.localdate()
        completed = self._work_order(
            company=company,
            piano=concert_grand,
            technician=users['demo_technician'],
            marker='[DEMO] Completed concert tuning',
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type=TaskType.TUNING,
            status=WorkOrder.Status.COMPLETE,
            priority=WorkOrder.Priority.HIGH,
            due_date=today - timedelta(days=3),
            completed_date=today - timedelta(days=2),
        )
        self._work_order(
            company=company,
            piano=recital_grand,
            technician=users['demo_technician'],
            marker='[DEMO] Regulation before student recital',
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type=TaskType.REGULATION,
            status=WorkOrder.Status.IN_PROGRESS,
            priority=WorkOrder.Priority.NORMAL,
            due_date=today + timedelta(days=4),
        )
        self._work_order(
            company=company,
            piano=studio_upright,
            technician=None,
            marker='[DEMO] Sticky key reported by faculty',
            order_type=WorkOrder.OrderType.REQUEST,
            task_type=TaskType.OTHER,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.HIGH,
            due_date=today + timedelta(days=1),
        )
        self._work_order(
            company=company,
            piano=concert_grand,
            technician=users['demo_technician'],
            marker='[DEMO] Replace worn stage caster',
            order_type=WorkOrder.OrderType.REQUEST,
            task_type=TaskType.OTHER,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            due_date=today + timedelta(days=14),
        )

        log, _ = MaintenanceLog.objects.update_or_create(
            company=company,
            work_order=completed,
            work_performed='[DEMO] Tuned to A440 and stabilized unisons.',
            defaults={
                'technician': users['demo_technician'],
                'piano': concert_grand,
                'hours_worked': Decimal('2.25'),
                'notes': 'Instrument ready for rehearsal.',
            },
        )
        PartUsed.objects.update_or_create(
            company=company,
            log=log,
            part=tuning_pin,
            defaults={'quantity_used': 2, 'cost_at_time': tuning_pin.unit_cost},
        )

        reading, _ = ConditionReading.objects.update_or_create(
            company=company,
            piano=concert_grand,
            notes='[DEMO] Post-service condition reading.',
            defaults={
                'log': log,
                'overall_rating': ConditionLevel.GOOD,
                'regulation_condition': ConditionLevel.GOOD,
                'voicing_condition': ConditionLevel.FAIR,
                'case_condition': ConditionLevel.EXCELLENT,
                'pitch_before_cents': Decimal('-7.50'),
                'pitch_after_cents': Decimal('0.00'),
                'humidity_pct': Decimal('44.00'),
                'temperature_f': Decimal('70.00'),
                'recorded_at': timezone.now() - timedelta(days=2),
            },
        )
        reading.update_piano_current_state()

        CompanyInvitation.objects.update_or_create(
            company=company,
            email='invited-tech@overtone-demo.invalid',
            status=CompanyInvitation.Status.PENDING,
            defaults={
                'first_name': 'Jamie',
                'last_name': 'Invitee',
                'role_admin': False,
                'role_technician': True,
                'invited_by': users['demo_admin'],
                'expires_at': timezone.now() + timedelta(days=7),
            },
        )
        return company

    @staticmethod
    def _venue(company, organization, name, address):
        venue, _ = Venue.objects.update_or_create(
            company=company,
            name=name,
            defaults={'organization': organization, 'address': address},
        )
        return venue

    @staticmethod
    def _piano(company, venue, name, make, piano_type, **defaults):
        piano, _ = Piano.objects.update_or_create(
            company=company,
            name=name,
            defaults={
                'venue': venue,
                'make': make,
                'piano_type': piano_type,
                **defaults,
            },
        )
        return piano

    @staticmethod
    def _part(company, name, part_number, unit_cost, stock_quantity, reorder_threshold):
        part, _ = Part.objects.update_or_create(
            company=company,
            name=name,
            defaults={
                'part_number': part_number,
                'supplier': 'Overtone Demo Supply',
                'unit_cost': Decimal(unit_cost),
                'stock_quantity': stock_quantity,
                'reorder_threshold': reorder_threshold,
            },
        )
        return part

    @staticmethod
    def _work_order(**values):
        marker = values.pop('marker')
        company = values.pop('company')
        work_order = WorkOrder.objects.filter(company=company, description=marker).first()
        if work_order is None:
            work_order = WorkOrder(company=company, description=marker)
        for field, value in values.items():
            if field == 'technician':
                work_order.assigned_tech = value
            else:
                setattr(work_order, field, value)
        work_order.save()
        return work_order
