from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from maintenance.models import (
    CompanySettings,
    ConditionLevel,
    ConditionReading,
    MaintenanceLog,
    MaintenanceRequest,
    MaintenanceSchedule,
    Organization,
    Part,
    PartUsed,
    Piano,
    ScheduleTemplate,
    Tag,
    TaskType,
    Technician,
    Venue,
    WorkOrder,
)


DEMO_PASSWORD = "DemoPass123"


class Command(BaseCommand):
    help = "Reset the database to a realistic demo dataset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Confirm that existing app data should be deleted and replaced.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError(
                "This deletes existing app data. Re-run with --yes to confirm."
            )

        self._clear_existing_data()
        today = timezone.localdate()

        CompanySettings.objects.create(
            company_name="Overtone Piano Service",
            address="421 Tuning Fork Lane\nChicago, IL 60605",
            phone="(312) 555-0148",
            email="dispatch@overtone.example",
            default_labor_rate=Decimal("95.00"),
        )

        admin = Technician.objects.create_user(
            username="demo-admin",
            password=DEMO_PASSWORD,
            first_name="Avery",
            last_name="Cole",
            email="avery@overtone.example",
            role_admin=True,
            role_technician=True,
            is_staff=True,
        )
        tech_mina = Technician.objects.create_user(
            username="mina-tech",
            password=DEMO_PASSWORD,
            first_name="Mina",
            last_name="Park",
            email="mina@overtone.example",
            role_admin=False,
            role_technician=True,
        )
        tech_luis = Technician.objects.create_user(
            username="luis-tech",
            password=DEMO_PASSWORD,
            first_name="Luis",
            last_name="Reyes",
            email="luis@overtone.example",
            role_admin=False,
            role_technician=True,
        )

        district = Organization.objects.create(
            name="North Shore Arts Academy",
            short_name="NSAA",
            address="810 Lakeview Ave\nEvanston, IL 60201",
            contact_name="Dr. Elaine Murphy",
            contact_email="emurphy@nsaa.example",
            contact_phone="(847) 555-0194",
            notes="High-use teaching fleet. Academic calendar peaks in October and April.",
        )
        hall_org = Organization.objects.create(
            name="Riverside Performing Arts Center",
            short_name="RPAC",
            address="220 W Riverfront Dr\nChicago, IL 60606",
            contact_name="Jordan Kim",
            contact_email="jordan@rpac.example",
            contact_phone="(312) 555-0171",
            notes="Concert instruments require pre-event touch-ups and humidity monitoring.",
        )
        studio_org = Organization.objects.create(
            name="South Loop Community Music",
            short_name="SLCM",
            address="64 E 18th St\nChicago, IL 60616",
            contact_name="Patricia Gomez",
            contact_email="pgomez@slcm.example",
            contact_phone="(312) 555-0126",
        )

        venues = {
            "conservatory": Venue.objects.create(
                organization=district,
                name="Conservatory Building",
                short_name="Conservatory",
                address="810 Lakeview Ave\nEvanston, IL 60201",
                on_site_contact="Nora Bell, Facilities Coordinator, (847) 555-0180",
                parking_notes="Use loading zone off Maple after 3 PM.",
                access_notes="Check in at security desk. Practice wing requires staff badge.",
            ),
            "recital": Venue.objects.create(
                organization=district,
                name="East Recital Hall",
                short_name="ERH",
                address="812 Lakeview Ave\nEvanston, IL 60201",
                on_site_contact="Nora Bell, Facilities Coordinator, (847) 555-0180",
                parking_notes="Street parking before 8 AM; dock available by appointment.",
                access_notes="Stage key stored in hall office lockbox.",
            ),
            "riverside": Venue.objects.create(
                organization=hall_org,
                name="Mainstage Hall",
                short_name="Mainstage",
                address="220 W Riverfront Dr\nChicago, IL 60606",
                on_site_contact="Sam Patel, Stage Manager, (312) 555-0142",
                parking_notes="Freight elevator entrance on Wells.",
                access_notes="Coordinate all stage access around rehearsals.",
            ),
            "south_loop": Venue.objects.create(
                organization=studio_org,
                name="South Loop Teaching Studios",
                short_name="Teaching Studios",
                address="64 E 18th St\nChicago, IL 60616",
                on_site_contact="Kara Nguyen, Studio Manager, (312) 555-0199",
                parking_notes="Metered parking on 18th; staff lot after 6 PM.",
                access_notes="Front desk can unlock rooms A-D.",
            ),
        }

        tags = {
            name: Tag.objects.create(name=name)
            for name in [
                "Concert",
                "Practice Room",
                "Teaching",
                "Humidity Watch",
                "Needs Regulation",
                "Recently Serviced",
            ]
        }

        pianos = [
            self._create_piano(
                venues["riverside"],
                "Mainstage Steinway D",
                "Steinway & Sons",
                "Model D",
                "584219",
                Piano.PianoType.GRAND,
                2006,
                "Stage",
                "Center stage",
                today - timedelta(days=18),
                today + timedelta(days=110),
                today + timedelta(days=42),
                today - timedelta(days=6),
                [tags["Concert"], tags["Humidity Watch"]],
                "Flagship concert grand. Tune before ticketed performances.",
            ),
            self._create_piano(
                venues["recital"],
                "Recital Yamaha C7",
                "Yamaha",
                "C7",
                "E312884",
                Piano.PianoType.GRAND,
                1998,
                "Performance Wing",
                "Recital platform",
                today + timedelta(days=9),
                today + timedelta(days=45),
                today + timedelta(days=74),
                today + timedelta(days=15),
                [tags["Concert"], tags["Recently Serviced"]],
                "Reliable recital instrument; action feels slightly heavy in upper register.",
            ),
            self._create_piano(
                venues["conservatory"],
                "Room 214 Kawai Upright",
                "Kawai",
                "K-300",
                "F091623",
                Piano.PianoType.UPRIGHT,
                2019,
                "Practice Wing",
                "Room 214",
                today - timedelta(days=3),
                today + timedelta(days=160),
                today + timedelta(days=100),
                today + timedelta(days=2),
                [tags["Practice Room"], tags["Teaching"]],
                "Heavy daily student use; bench hardware loosens frequently.",
            ),
            self._create_piano(
                venues["conservatory"],
                "Theory Lab Everett",
                "Everett",
                "Studio 45",
                "451902",
                Piano.PianoType.UPRIGHT,
                1977,
                "Academic Wing",
                "Theory Lab",
                today + timedelta(days=31),
                today - timedelta(days=20),
                today + timedelta(days=88),
                today + timedelta(days=12),
                [tags["Teaching"], tags["Needs Regulation"]],
                "Older upright with uneven repetition; good candidate for summer action work.",
            ),
            self._create_piano(
                venues["south_loop"],
                "Studio B Boston GP-178",
                "Boston",
                "GP-178",
                "178430",
                Piano.PianoType.GRAND,
                2014,
                "Studio Hall",
                "Studio B",
                today + timedelta(days=20),
                today + timedelta(days=70),
                today - timedelta(days=8),
                today + timedelta(days=25),
                [tags["Teaching"], tags["Humidity Watch"]],
                "Private lesson grand; tone has brightened after winter heating season.",
            ),
            self._create_piano(
                venues["south_loop"],
                "Digital Lab Clavinova",
                "Yamaha",
                "CLP-775",
                "CLP775-44218",
                Piano.PianoType.DIGITAL,
                2021,
                "Digital Lab",
                "Keyboard station 6",
                None,
                None,
                None,
                today + timedelta(days=60),
                [tags["Teaching"]],
                "Digital instrument tracked for cleaning and pedal/cable issues.",
            ),
        ]

        templates = [
            ScheduleTemplate.objects.create(
                name="Concert Tuning - 6 Month",
                task_name="Full concert tuning",
                task_type=TaskType.TUNING,
                interval_days=180,
                warning_days_before=21,
                description="Standard tuning cycle for performance instruments.",
            ),
            ScheduleTemplate.objects.create(
                name="Annual Regulation Review",
                task_name="Action regulation review",
                task_type=TaskType.REGULATION,
                interval_days=365,
                warning_days_before=30,
                description="Assess touch weight, repetition, let-off, and key dip.",
            ),
            ScheduleTemplate.objects.create(
                name="Quarterly Cleaning",
                task_name="Cabinet, keybed, and pedal cleaning",
                task_type=TaskType.CLEANING,
                interval_days=90,
                warning_days_before=10,
                description="Dust removal and basic hardware check.",
            ),
        ]

        for piano in pianos:
            MaintenanceSchedule.objects.create(
                piano=piano,
                template=templates[0],
                task_name=templates[0].task_name,
                task_type=templates[0].task_type,
                interval_days=templates[0].interval_days,
                warning_days_before=templates[0].warning_days_before,
                last_service_date=today - timedelta(days=185),
            )
            if piano.piano_type != Piano.PianoType.DIGITAL:
                MaintenanceSchedule.objects.create(
                    piano=piano,
                    template=templates[1],
                    task_name=templates[1].task_name,
                    task_type=templates[1].task_type,
                    interval_days=templates[1].interval_days,
                    warning_days_before=templates[1].warning_days_before,
                    last_service_date=today - timedelta(days=340),
                )
            MaintenanceSchedule.objects.create(
                piano=piano,
                template=templates[2],
                task_name=templates[2].task_name,
                task_type=templates[2].task_type,
                interval_days=templates[2].interval_days,
                warning_days_before=templates[2].warning_days_before,
                last_service_date=today - timedelta(days=82),
            )

        parts = {
            "strings": Part.objects.create(
                name="Mapes bass string set",
                part_number="MBS-STD",
                supplier="PianoTek",
                unit_cost=Decimal("84.50"),
                stock_quantity=2,
                reorder_threshold=1,
            ),
            "felt": Part.objects.create(
                name="Key bushing felt",
                part_number="KBF-RED",
                supplier="Schaff",
                unit_cost=Decimal("18.25"),
                stock_quantity=6,
                reorder_threshold=3,
            ),
            "casters": Part.objects.create(
                name="Grand caster cup set",
                part_number="GCC-BLK",
                supplier="Jansen",
                unit_cost=Decimal("42.00"),
                stock_quantity=1,
                reorder_threshold=2,
            ),
            "pedal": Part.objects.create(
                name="Pedal lyre screw kit",
                part_number="PLS-14",
                supplier="PianoTek",
                unit_cost=Decimal("12.75"),
                stock_quantity=9,
                reorder_threshold=4,
            ),
        }

        self._create_condition_reading(
            pianos[0],
            ConditionLevel.GOOD,
            pitch=Decimal("-4.50"),
            humidity=Decimal("38.00"),
            temperature=Decimal("71.00"),
            notes="Bass stable; treble drifting sharp under stage lights.",
            recorded_at=timezone.now() - timedelta(days=10),
        )
        self._create_condition_reading(
            pianos[3],
            ConditionLevel.FAIR,
            pitch=Decimal("-8.25"),
            humidity=Decimal("31.00"),
            temperature=Decimal("73.00"),
            notes="Action regulation is uneven; hammers show grooving.",
            recorded_at=timezone.now() - timedelta(days=22),
        )
        self._create_condition_reading(
            pianos[4],
            ConditionLevel.GOOD,
            pitch=Decimal("3.75"),
            humidity=Decimal("44.00"),
            temperature=Decimal("70.00"),
            notes="Voicing is brighter than preferred for lessons.",
            recorded_at=timezone.now() - timedelta(days=15),
        )

        completed = WorkOrder.objects.create(
            piano=pianos[1],
            assigned_tech=tech_mina,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type=TaskType.TUNING,
            status=WorkOrder.Status.COMPLETE,
            priority=WorkOrder.Priority.NORMAL,
            description="Pre-recital tuning and pedal check.",
            due_date=today - timedelta(days=12),
            completed_date=today - timedelta(days=11),
        )
        log = MaintenanceLog.objects.create(
            work_order=completed,
            technician=tech_mina,
            piano=pianos[1],
            hours_worked=Decimal("2.25"),
            work_performed="Completed full tuning, tightened pedal lyre screws, and cleaned keytops.",
            notes="Instrument ready for faculty recital series.",
        )
        PartUsed.objects.create(
            log=log,
            part=parts["pedal"],
            quantity_used=1,
            cost_at_time=parts["pedal"].unit_cost,
        )

        WorkOrder.objects.create(
            piano=pianos[0],
            assigned_tech=admin,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type=TaskType.TUNING,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.HIGH,
            description="Concert tuning due before weekend symphony rental.",
            due_date=today - timedelta(days=2),
        )
        WorkOrder.objects.create(
            piano=pianos[2],
            assigned_tech=tech_luis,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type=TaskType.CLEANING,
            status=WorkOrder.Status.IN_PROGRESS,
            priority=WorkOrder.Priority.NORMAL,
            description="Quarterly cleaning plus loose bench hardware check.",
            due_date=today + timedelta(days=2),
        )
        WorkOrder.objects.create(
            piano=pianos[3],
            assigned_tech=None,
            order_type=WorkOrder.OrderType.PREVENTIVE,
            task_type=TaskType.REGULATION,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.HIGH,
            description="Regulation overdue; uneven repetition reported by theory faculty.",
            due_date=today - timedelta(days=20),
        )
        WorkOrder.objects.create(
            piano=pianos[4],
            assigned_tech=tech_mina,
            order_type=WorkOrder.OrderType.REQUEST,
            task_type=TaskType.VOICING,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description="Teacher reports tone is too bright in middle register.",
            due_date=today + timedelta(days=7),
        )

        request_wo = WorkOrder.objects.create(
            piano=pianos[5],
            assigned_tech=None,
            order_type=WorkOrder.OrderType.REQUEST,
            task_type=TaskType.CLEANING,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.LOW,
            description="Digital lab pedal cable intermittently disconnects.",
            due_date=today + timedelta(days=14),
        )
        MaintenanceRequest.objects.create(
            piano=pianos[5],
            reported_by_name="Jules Turner",
            reported_by_email="jules@slcm.example",
            issue_description="Sustain pedal at station 6 cuts in and out during class.",
            status=MaintenanceRequest.RequestStatus.ASSIGNED,
            work_order=request_wo,
        )
        MaintenanceRequest.objects.create(
            piano=pianos[0],
            reported_by_name="Sam Patel",
            reported_by_email="sam@rpac.example",
            issue_description="Stage grand cover latch is sticking and may scratch the rim.",
            status=MaintenanceRequest.RequestStatus.NEW,
        )

        self.stdout.write(self.style.SUCCESS("Demo data reset complete."))
        self.stdout.write(
            "Login: demo-admin / {password}".format(password=DEMO_PASSWORD)
        )
        self.stdout.write(
            "Created {pianos} pianos, {work_orders} work orders, and {parts} parts.".format(
                pianos=Piano.objects.count(),
                work_orders=WorkOrder.objects.count(),
                parts=Part.objects.count(),
            )
        )

    def _clear_existing_data(self):
        MaintenanceRequest.objects.all().delete()
        PartUsed.objects.all().delete()
        ConditionReading.objects.all().delete()
        MaintenanceLog.objects.all().delete()
        WorkOrder.objects.all().delete()
        MaintenanceSchedule.objects.all().delete()
        ScheduleTemplate.objects.all().delete()
        Part.objects.all().delete()
        Piano.objects.all().delete()
        Venue.objects.all().delete()
        Organization.objects.all().delete()
        Tag.objects.all().delete()
        CompanySettings.objects.all().delete()
        Technician.objects.all().delete()

    def _create_piano(
        self,
        venue,
        name,
        make,
        model,
        serial_number,
        piano_type,
        year_built,
        section,
        room,
        next_tuning_due,
        next_regulation_due,
        next_voicing_due,
        next_cleaning_due,
        tags,
        notes,
    ):
        piano = Piano.objects.create(
            venue=venue,
            name=name,
            make=make,
            model=model,
            serial_number=serial_number,
            piano_type=piano_type,
            year_built=year_built,
            year_acquired=max(year_built + 1, 2010) if year_built else None,
            section=section,
            room=room,
            room_description="Ask front desk for room access if the door is locked.",
            room_access_notes="Best service windows are weekday mornings.",
            next_tuning_due=next_tuning_due,
            next_regulation_due=next_regulation_due,
            next_voicing_due=next_voicing_due,
            next_cleaning_due=next_cleaning_due,
            notes=notes,
        )
        piano.tags.set(tags)
        return piano

    def _create_condition_reading(
        self,
        piano,
        rating,
        pitch,
        humidity,
        temperature,
        notes,
        recorded_at,
    ):
        reading = ConditionReading.objects.create(
            piano=piano,
            pitch_before_cents=pitch - Decimal("1.50"),
            pitch_after_cents=pitch,
            humidity_pct=humidity,
            temperature_f=temperature,
            overall_rating=rating,
            regulation_condition=rating,
            voicing_condition=rating,
            belly_condition=ConditionLevel.GOOD,
            soundboard_condition=ConditionLevel.GOOD,
            pinblock_condition=ConditionLevel.GOOD,
            strings_condition=rating,
            hammers_condition=rating,
            keys_condition=ConditionLevel.GOOD,
            pedals_condition=ConditionLevel.GOOD,
            case_condition=ConditionLevel.GOOD,
            notes=notes,
            recorded_at=recorded_at,
        )
        reading.update_piano_current_state()
        return reading
