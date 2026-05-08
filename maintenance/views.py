import csv
import io
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib import messages

from .models import (
    Organization, Venue, Piano, WorkOrder, MaintenanceRequest,
    MaintenanceSchedule, ScheduleTemplate, ConditionReading, ServiceVisit,
    Technician, Part, PartUsed, MaintenanceLog, TaskType, Photo,
)
from .forms import (
    OrganizationForm, VenueForm, PianoForm, WorkOrderForm, WorkOrderCompleteForm,
    ConditionReadingForm, ScheduleTemplateForm,
    ServiceVisitForm, ServiceVisitCompleteForm, PartForm,
)


# ── Public (no login) ──────────────────────────────────────────────

def maintenance_request_form(request, token):
    piano = get_object_or_404(Piano, qr_code_token=token)

    if request.method == 'POST':
        issue = request.POST.get('issue_description', '').strip()
        name  = request.POST.get('reported_by_name', '').strip()
        email = request.POST.get('reported_by_email', '').strip()
        if issue:
            mr = MaintenanceRequest.objects.create(
                piano=piano,
                reported_by_name=name,
                reported_by_email=email,
                issue_description=issue,
                status='Assigned',
            )
            wo = WorkOrder.objects.create(
                piano=piano,
                order_type=WorkOrder.OrderType.REQUEST,
                status=WorkOrder.Status.OPEN,
                priority=WorkOrder.Priority.NORMAL,
                description=issue,
            )
            mr.work_order = wo
            mr.save()
            return HttpResponse(
                '<h2>Thank you — your request has been submitted.</h2>'
                '<p>A work order has been created and our team will follow up.</p>',
                content_type='text/html'
            )

    return render(request, 'maintenance/maintenance_request_form.html',
                  {'piano': piano})


# ── Dashboard ──────────────────────────────────────────────────────

@login_required
def dashboard(request):
    today = date.today()
    month_start = today.replace(day=1)

    overdue_count = WorkOrder.objects.filter(
        status__in=[WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS],
        due_date__lt=today,
    ).count()

    open_wo_count = WorkOrder.objects.filter(status=WorkOrder.Status.OPEN).count()
    in_progress_count = WorkOrder.objects.filter(status=WorkOrder.Status.IN_PROGRESS).count()
    pending_request_count = MaintenanceRequest.objects.filter(status=MaintenanceRequest.RequestStatus.NEW).count()
    piano_count = Piano.objects.filter(is_active=True).count()
    venue_count = Venue.objects.count()
    org_count = Organization.objects.count()
    completed_this_month = WorkOrder.objects.filter(
        status=WorkOrder.Status.COMPLETE,
        completed_date__gte=month_start,
    ).count()

    recent_work_orders = (
        WorkOrder.objects
        .select_related('piano', 'piano__venue')
        .order_by('-created_at')[:10]
    )

    return render(request, 'maintenance/dashboard.html', {
        'active_nav': 'dashboard',
        'overdue_count': overdue_count,
        'open_wo_count': open_wo_count,
        'in_progress_count': in_progress_count,
        'pending_request_count': pending_request_count,
        'piano_count': piano_count,
        'venue_count': venue_count,
        'org_count': org_count,
        'completed_this_month': completed_this_month,
        'recent_work_orders': recent_work_orders,
    })


# ── Pianos ─────────────────────────────────────────────────────────

@login_required
def piano_list(request):
    today = date.today()
    soon = today + timedelta(days=30)

    qs = Piano.objects.filter(is_active=True).select_related('venue').prefetch_related('photos')

    search_query = request.GET.get('q', '').strip()
    venue_filter = request.GET.get('venue', '')
    type_filter = request.GET.get('type', '')

    if search_query:
        qs = qs.filter(
            Q(name__icontains=search_query) |
            Q(make__icontains=search_query) |
            Q(serial_number__icontains=search_query)
        )
    if venue_filter:
        qs = qs.filter(venue_id=venue_filter)
    if type_filter:
        qs = qs.filter(piano_type=type_filter)

    return render(request, 'maintenance/piano_list.html', {
        'active_nav': 'pianos',
        'pianos': qs,
        'venues': Venue.objects.all(),
        'search_query': search_query,
        'venue_filter': venue_filter,
        'type_filter': type_filter,
        'today': today,
        'soon': soon,
    })


def _piano_context(piano):
    today = date.today()
    condition_fields = [
        ('Regulation', piano.regulation_condition),
        ('Voicing', piano.voicing_condition),
        ('Belly', piano.belly_condition),
        ('Soundboard', piano.soundboard_condition),
        ('Pinblock', piano.pinblock_condition),
        ('Strings', piano.strings_condition),
        ('Hammers', piano.hammers_condition),
        ('Keys', piano.keys_condition),
        ('Pedals', piano.pedals_condition),
        ('Case', piano.case_condition),
    ]
    return {
        'active_nav': 'pianos',
        'piano': piano,
        'condition_fields': condition_fields,
        'has_condition': any(v for _, v in condition_fields),
        'maintenance_intervals': [
            ('Tuning', piano.tuning_interval_value, piano.tuning_interval_unit, piano.next_tuning_due),
            ('Regulation', piano.regulation_interval_value, piano.regulation_interval_unit, piano.next_regulation_due),
            ('Voicing', piano.voicing_interval_value, piano.voicing_interval_unit, piano.next_voicing_due),
            ('Cleaning', piano.cleaning_interval_value, piano.cleaning_interval_unit, piano.next_cleaning_due),
        ],
        'work_orders': piano.work_orders.select_related('assigned_tech').order_by('-created_at')[:20],
        'condition_readings': piano.condition_readings.order_by('-recorded_at')[:20],
        'custom_schedules': piano.schedules.all(),
        'today': today,
    }


@login_required
def piano_detail(request, pk):
    piano = get_object_or_404(Piano.objects.select_related('venue'), pk=pk)
    ctx = _piano_context(piano)
    ctx['qr_url'] = request.build_absolute_uri(f'/maintenance_request/{piano.qr_code_token}/')
    ctx['photos'] = piano.photos.all()
    return render(request, 'maintenance/piano_detail.html', ctx)


@login_required
def piano_tab(request, pk, tab):
    piano = get_object_or_404(Piano.objects.select_related('venue'), pk=pk)
    ctx = _piano_context(piano)
    templates = {
        'overview': 'maintenance/partials/piano_tab_overview.html',
        'work-orders': 'maintenance/partials/piano_tab_workorders.html',
        'maintenance': 'maintenance/partials/piano_tab_maintenance.html',
        'condition': 'maintenance/partials/piano_tab_condition.html',
    }
    template = templates.get(tab, templates['overview'])
    return render(request, template, ctx)


@login_required
def piano_create(request):
    if request.method == 'POST':
        form = PianoForm(request.POST)
        if form.is_valid():
            piano = form.save()
            messages.success(request, f'Piano "{piano.name}" created.')
            return redirect('piano_detail', pk=piano.pk)
    else:
        form = PianoForm()

    return render(request, 'maintenance/piano_form.html', {
        'active_nav': 'pianos',
        'form': form,
        'piano': None,
        'venues': Venue.objects.all(),
        'type_choices': Piano.PianoType.choices,
    })


@login_required
def piano_edit(request, pk):
    piano = get_object_or_404(Piano, pk=pk)

    if request.method == 'POST':
        form = PianoForm(request.POST, instance=piano)
        if form.is_valid():
            form.save()
            messages.success(request, f'Piano "{piano.name}" updated.')
            return redirect('piano_detail', pk=piano.pk)
    else:
        form = PianoForm(instance=piano)

    return render(request, 'maintenance/piano_form.html', {
        'active_nav': 'pianos',
        'form': form,
        'piano': piano,
        'venues': Venue.objects.all(),
        'type_choices': Piano.PianoType.choices,
    })


# ── Organizations ─────────────────────────────────────────────────

@login_required
def organization_list(request):
    organizations = Organization.objects.annotate(venue_count=Count('venues'))
    return render(request, 'maintenance/organization_list.html', {
        'active_nav': 'organizations',
        'organizations': organizations,
    })


@login_required
def organization_detail(request, pk):
    organization = get_object_or_404(Organization, pk=pk)
    venues = Venue.objects.filter(organization=organization).annotate(piano_count=Count('pianos'))
    return render(request, 'maintenance/organization_detail.html', {
        'active_nav': 'organizations',
        'organization': organization,
        'venues': venues,
    })


@login_required
def organization_create(request):
    if request.method == 'POST':
        form = OrganizationForm(request.POST)
        if form.is_valid():
            org = form.save()
            messages.success(request, f'Organization "{org.name}" created.')
            return redirect('organization_detail', pk=org.pk)
    else:
        form = OrganizationForm()

    return render(request, 'maintenance/organization_form.html', {
        'active_nav': 'organizations',
        'form': form,
        'organization': None,
    })


@login_required
def organization_edit(request, pk):
    organization = get_object_or_404(Organization, pk=pk)

    if request.method == 'POST':
        form = OrganizationForm(request.POST, instance=organization)
        if form.is_valid():
            form.save()
            messages.success(request, f'Organization "{organization.name}" updated.')
            return redirect('organization_detail', pk=organization.pk)
    else:
        form = OrganizationForm(instance=organization)

    return render(request, 'maintenance/organization_form.html', {
        'active_nav': 'organizations',
        'form': form,
        'organization': organization,
    })


# ── Venues ─────────────────────────────────────────────────────────

@login_required
def venue_list(request):
    venues = Venue.objects.select_related('organization').annotate(piano_count=Count('pianos'))
    return render(request, 'maintenance/venue_list.html', {
        'active_nav': 'venues',
        'venues': venues,
    })


@login_required
def venue_detail(request, pk):
    venue = get_object_or_404(Venue.objects.select_related('organization'), pk=pk)
    pianos = Piano.objects.filter(venue=venue, is_active=True).select_related('venue')
    open_wo_count = WorkOrder.objects.filter(
        piano__venue=venue,
        status__in=[WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS],
    ).count()
    return render(request, 'maintenance/venue_detail.html', {
        'active_nav': 'venues',
        'venue': venue,
        'pianos': pianos,
        'open_wo_count': open_wo_count,
    })


@login_required
def venue_create(request):
    if request.method == 'POST':
        form = VenueForm(request.POST)
        if form.is_valid():
            venue = form.save()
            messages.success(request, f'Venue "{venue.name}" created.')
            return redirect('venue_detail', pk=venue.pk)
    else:
        form = VenueForm()

    return render(request, 'maintenance/venue_form.html', {
        'active_nav': 'venues',
        'form': form,
        'venue': None,
        'organizations': Organization.objects.all(),
    })


@login_required
def venue_edit(request, pk):
    venue = get_object_or_404(Venue, pk=pk)

    if request.method == 'POST':
        form = VenueForm(request.POST, instance=venue)
        if form.is_valid():
            form.save()
            messages.success(request, f'Venue "{venue.name}" updated.')
            return redirect('venue_detail', pk=venue.pk)
    else:
        form = VenueForm(instance=venue)

    return render(request, 'maintenance/venue_form.html', {
        'active_nav': 'venues',
        'form': form,
        'venue': venue,
        'organizations': Organization.objects.all(),
    })


# ── Work Orders ───────────────────────────────────────────────────

@login_required
def workorder_list(request):
    today = date.today()
    qs = (
        WorkOrder.objects
        .select_related('piano', 'piano__venue', 'assigned_tech')
        .order_by('-created_at')
    )

    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    type_filter = request.GET.get('type', '')

    if search_query:
        qs = qs.filter(
            Q(description__icontains=search_query) |
            Q(piano__name__icontains=search_query) |
            Q(piano__venue__name__icontains=search_query)
        )
    if status_filter:
        qs = qs.filter(status=status_filter)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    if type_filter:
        qs = qs.filter(order_type=type_filter)

    return render(request, 'maintenance/workorder_list.html', {
        'active_nav': 'workorders',
        'work_orders': qs,
        'search_query': search_query,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'type_filter': type_filter,
        'status_choices': WorkOrder.Status.choices,
        'priority_choices': WorkOrder.Priority.choices,
        'type_choices': WorkOrder.OrderType.choices,
        'today': today,
    })


@login_required
def workorder_detail(request, pk):
    wo = get_object_or_404(
        WorkOrder.objects.select_related('piano', 'piano__venue', 'assigned_tech'),
        pk=pk,
    )
    logs = wo.logs.select_related('technician').order_by('-logged_at')
    technicians = Technician.objects.filter(is_active=True).order_by('first_name', 'last_name')
    return render(request, 'maintenance/workorder_detail.html', {
        'active_nav': 'workorders',
        'wo': wo,
        'logs': logs,
        'technicians': technicians,
        'today': date.today(),
    })


@login_required
def workorder_create(request):
    if request.method == 'POST':
        form = WorkOrderForm(request.POST)
        if form.is_valid():
            wo = form.save()
            messages.success(request, f'Work Order WO-{wo.pk} created.')
            return redirect('workorder_detail', pk=wo.pk)
    else:
        initial = {}
        piano_pk = request.GET.get('piano')
        if piano_pk:
            initial['piano'] = piano_pk
        form = WorkOrderForm(initial=initial)

    return render(request, 'maintenance/workorder_form.html', {
        'active_nav': 'workorders',
        'form': form,
        'pianos': Piano.objects.filter(is_active=True).select_related('venue'),
        'venues': Venue.objects.all(),
        'technicians': Technician.objects.filter(is_active=True),
        'type_choices': WorkOrder.OrderType.choices,
        'task_type_choices': TaskType.choices,
        'status_choices': WorkOrder.Status.choices,
        'priority_choices': WorkOrder.Priority.choices,
    })


@login_required
def workorder_assign(request, pk):
    wo = get_object_or_404(WorkOrder, pk=pk)
    if request.method == 'POST':
        tech_id = request.POST.get('assigned_tech')
        if tech_id:
            wo.assigned_tech_id = int(tech_id)
        else:
            wo.assigned_tech = None
        if wo.status == WorkOrder.Status.OPEN and wo.assigned_tech_id:
            wo.status = WorkOrder.Status.IN_PROGRESS
        wo.save()
    technicians = Technician.objects.filter(is_active=True).order_by('first_name', 'last_name')
    return render(request, 'maintenance/partials/workorder_assign_cell.html', {
        'wo': wo,
        'technicians': technicians,
    })


@login_required
def workorder_complete(request, pk):
    wo = get_object_or_404(
        WorkOrder.objects.select_related('piano', 'assigned_tech'),
        pk=pk,
    )
    parts = Part.objects.all().order_by('name')

    if request.method == 'POST':
        form = WorkOrderCompleteForm(request.POST)
        if form.is_valid():
            today_date = date.today()
            # Create the maintenance log
            tech = wo.assigned_tech or request.user
            log = MaintenanceLog.objects.create(
                work_order=wo,
                technician=tech,
                piano=wo.piano,
                hours_worked=form.cleaned_data['hours_worked'],
                work_performed=form.cleaned_data['work_performed'],
                notes=form.cleaned_data['notes'],
            )

            # Handle photo uploads
            for f in request.FILES.getlist('photos'):
                Photo.objects.create(work_order=wo, image=f, caption='')

            # Handle parts used
            part_ids = request.POST.getlist('part_id')
            part_qtys = request.POST.getlist('part_qty')
            for pid, qty in zip(part_ids, part_qtys):
                if pid and qty:
                    try:
                        part = Part.objects.get(pk=int(pid))
                        qty_int = int(qty)
                        if qty_int > 0:
                            PartUsed.objects.create(
                                log=log,
                                part=part,
                                quantity_used=qty_int,
                                cost_at_time=part.unit_cost,
                            )
                            part.stock_quantity = max(0, part.stock_quantity - qty_int)
                            part.save(update_fields=['stock_quantity'])
                    except (Part.DoesNotExist, ValueError):
                        pass

            # Mark complete
            wo.status = WorkOrder.Status.COMPLETE
            wo.completed_date = today_date
            wo.save()

            # Advance the piano's maintenance schedule
            if wo.task_type:
                wo.piano.advance_schedule(wo.task_type, today_date)

            # Also update any custom MaintenanceSchedule entries
            if wo.schedule:
                wo.schedule.last_service_date = today_date
                wo.schedule.save(update_fields=['last_service_date'])

            # Handle inline condition reading if checkbox was checked
            if form.cleaned_data.get('include_condition'):
                condition_fields = [
                    'overall_rating',
                    'regulation_condition', 'voicing_condition',
                    'belly_condition', 'soundboard_condition',
                    'pinblock_condition', 'strings_condition',
                    'hammers_condition', 'keys_condition',
                    'pedals_condition', 'case_condition',
                    'pitch_before_cents', 'pitch_after_cents',
                    'humidity_pct', 'temperature_f',
                ]
                cr_data = {}
                for field in condition_fields:
                    val = form.cleaned_data.get(field)
                    if val not in (None, ''):
                        cr_data[field] = val
                cr_data['notes'] = form.cleaned_data.get('condition_notes', '')
                reading = ConditionReading.objects.create(
                    piano=wo.piano,
                    log=log,
                    **cr_data,
                )
                reading.update_piano_current_state()

            messages.success(request, f'Work Order WO-{wo.pk} completed.')
            return redirect('workorder_detail', pk=wo.pk)
    else:
        # Pre-fill condition fields from last reading (same logic as standalone)
        initial = {}
        last_reading = wo.piano.condition_readings.order_by('-recorded_at').first()
        if last_reading:
            initial['overall_rating'] = last_reading.overall_rating or ''
            for _, field_name in CONDITION_FIELD_LIST:
                initial[field_name] = getattr(last_reading, field_name) or ''
            if last_reading.humidity_pct is not None:
                initial['humidity_pct'] = last_reading.humidity_pct
            if last_reading.temperature_f is not None:
                initial['temperature_f'] = last_reading.temperature_f
        form = WorkOrderCompleteForm(initial=initial)

    # Build condition fields with values for template iteration
    condition_fields_with_values = [
        (label, field_name, form[field_name].value() or '')
        for label, field_name in CONDITION_FIELD_LIST
    ]

    return render(request, 'maintenance/workorder_complete.html', {
        'active_nav': 'workorders',
        'wo': wo,
        'form': form,
        'parts': parts,
        'condition_fields_with_values': condition_fields_with_values,
    })


# ── Photo Upload ─────────────────────────────────────────────────

@login_required
def piano_photo_upload(request, pk):
    piano = get_object_or_404(Piano, pk=pk)
    if request.method == 'POST':
        caption = request.POST.get('caption', '')
        files = request.FILES.getlist('photos')
        for f in files:
            is_profile = not piano.photos.exists()  # first photo = profile
            Photo.objects.create(piano=piano, image=f, caption=caption, is_profile_photo=is_profile)
        messages.success(request, f'{len(files)} photo(s) uploaded.')
        return redirect('piano_detail', pk=piano.pk)

    return render(request, 'maintenance/piano_photo_upload.html', {
        'active_nav': 'pianos',
        'piano': piano,
    })


@login_required
def piano_set_profile_photo(request, pk, photo_pk):
    piano = get_object_or_404(Piano, pk=pk)
    if request.method == 'POST':
        piano.photos.update(is_profile_photo=False)
        Photo.objects.filter(pk=photo_pk, piano=piano).update(is_profile_photo=True)
    return redirect('piano_detail', pk=piano.pk)


# ── Schedule Auto-Generation ────────────────────────────────────

def _generate_scheduled_work_orders():
    """
    Check all active pianos' built-in schedules and custom schedules.
    Create work orders for any that are due and don't already have an open WO.

    Bootstrap: if a piano has an interval configured but no next-due date,
    seed the due date to today so it becomes immediately due.

    Returns count of created WOs.
    """
    today = date.today()
    created = 0

    # Built-in schedules (tuning, regulation, voicing, cleaning)
    built_in_types = [
        ('Tuning', 'next_tuning_due', 'tuning_interval_value'),
        ('Regulation', 'next_regulation_due', 'regulation_interval_value'),
        ('Voicing', 'next_voicing_due', 'voicing_interval_value'),
        ('Cleaning', 'next_cleaning_due', 'cleaning_interval_value'),
    ]
    for piano in Piano.objects.filter(is_active=True):
        needs_save = []
        for task_type, due_field, interval_field in built_in_types:
            due_date = getattr(piano, due_field)
            interval_val = getattr(piano, interval_field)

            # Bootstrap: if interval is set but no due date, seed to today
            if due_date is None and interval_val:
                setattr(piano, due_field, today)
                needs_save.append(due_field)
                due_date = today

            if due_date and due_date <= today:
                # Check no open WO of this type exists
                exists = WorkOrder.objects.filter(
                    piano=piano,
                    task_type=task_type,
                    status__in=[WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS],
                ).exists()
                if not exists:
                    WorkOrder.objects.create(
                        piano=piano,
                        order_type=WorkOrder.OrderType.PREVENTIVE,
                        task_type=task_type,
                        status=WorkOrder.Status.OPEN,
                        priority=WorkOrder.Priority.NORMAL,
                        description=f'Scheduled {task_type.lower()}',
                        due_date=due_date,
                    )
                    created += 1

        if needs_save:
            piano.save(update_fields=needs_save)

    # Custom schedules
    for sched in MaintenanceSchedule.objects.filter(is_active=True).select_related('piano'):
        nd = sched.next_due
        if nd and nd <= today:
            exists = WorkOrder.objects.filter(
                piano=sched.piano,
                schedule=sched,
                status__in=[WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS],
            ).exists()
            if not exists:
                WorkOrder.objects.create(
                    piano=sched.piano,
                    order_type=WorkOrder.OrderType.PREVENTIVE,
                    task_type=sched.task_type,
                    status=WorkOrder.Status.OPEN,
                    priority=WorkOrder.Priority.NORMAL,
                    description=f'Scheduled: {sched.task_name}',
                    due_date=nd,
                    schedule=sched,
                )
                created += 1

    return created


# ── Slice 6: Schedule ────────────────────────────────────────────

@login_required
def schedule(request):
    today = date.today()
    soon = today + timedelta(days=30)

    # Auto-generate any due work orders
    generated = _generate_scheduled_work_orders()
    if generated:
        messages.info(request, f'{generated} scheduled work order(s) auto-created.')

    active_statuses = [WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS]
    active_wos = (
        WorkOrder.objects
        .filter(status__in=active_statuses)
        .select_related('piano', 'piano__venue', 'assigned_tech')
    )

    overdue = active_wos.filter(due_date__lt=today).order_by('due_date')
    due_soon = active_wos.filter(due_date__gte=today, due_date__lte=soon).order_by('due_date')
    upcoming = active_wos.filter(due_date__gt=soon).order_by('due_date')
    no_date = active_wos.filter(due_date__isnull=True).order_by('-created_at')

    return render(request, 'maintenance/schedule.html', {
        'active_nav': 'schedule',
        'overdue': overdue,
        'due_soon': due_soon,
        'upcoming': upcoming,
        'no_date': no_date,
        'today': today,
    })


# ── Slice 7: Requests ───────────────────────────────────────────

@login_required
def request_list(request):
    qs = (
        MaintenanceRequest.objects
        .select_related('piano', 'piano__venue', 'work_order')
        .order_by('-created_at')
    )

    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(request, 'maintenance/request_list.html', {
        'active_nav': 'requests',
        'requests': qs,
        'status_filter': status_filter,
        'status_choices': MaintenanceRequest.RequestStatus.choices,
    })


@login_required
def request_approve(request, pk):
    mr = get_object_or_404(MaintenanceRequest, pk=pk)
    if request.method == 'POST' and not mr.work_order:
        wo = WorkOrder.objects.create(
            piano=mr.piano,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description=mr.issue_description,
        )
        mr.work_order = wo
        mr.status = MaintenanceRequest.RequestStatus.ASSIGNED
        mr.save()
        messages.success(request, f'Request approved — WO-{wo.pk} created.')
    return redirect('request_list')


@login_required
def request_reject(request, pk):
    mr = get_object_or_404(MaintenanceRequest, pk=pk)
    if request.method == 'POST':
        mr.status = MaintenanceRequest.RequestStatus.RESOLVED
        mr.save()
        messages.success(request, 'Request marked as resolved.')
    return redirect('request_list')


# ── Slice 8: Condition Reading ───────────────────────────────────

CONDITION_FIELD_LIST = [
    ('Regulation', 'regulation_condition'),
    ('Voicing', 'voicing_condition'),
    ('Belly', 'belly_condition'),
    ('Soundboard', 'soundboard_condition'),
    ('Pinblock', 'pinblock_condition'),
    ('Strings', 'strings_condition'),
    ('Hammers', 'hammers_condition'),
    ('Keys', 'keys_condition'),
    ('Pedals', 'pedals_condition'),
    ('Case', 'case_condition'),
]


@login_required
def condition_reading_create(request, piano_pk):
    piano = get_object_or_404(Piano, pk=piano_pk)

    if request.method == 'POST':
        form = ConditionReadingForm(request.POST)
        if form.is_valid():
            reading = form.save(commit=False)
            reading.piano = piano
            reading.save()
            reading.update_piano_current_state()
            messages.success(request, 'Condition reading saved.')
            return redirect('piano_detail', pk=piano.pk)
    else:
        # Pre-fill from the most recent condition reading (except pitch fields)
        initial = {}
        last_reading = piano.condition_readings.order_by('-recorded_at').first()
        if last_reading:
            initial['overall_rating'] = last_reading.overall_rating
            for _, field_name in CONDITION_FIELD_LIST:
                initial[field_name] = getattr(last_reading, field_name)
            # Pre-fill environment (except pitch — those are per-visit)
            if last_reading.humidity_pct is not None:
                initial['humidity_pct'] = last_reading.humidity_pct
            if last_reading.temperature_f is not None:
                initial['temperature_f'] = last_reading.temperature_f
            # Pitch fields intentionally left blank
        form = ConditionReadingForm(initial=initial)

    # Build field list with current form values so template can set selected
    condition_fields_with_values = [
        (label, field_name, form[field_name].value() or '')
        for label, field_name in CONDITION_FIELD_LIST
    ]

    return render(request, 'maintenance/condition_reading_form.html', {
        'active_nav': 'pianos',
        'form': form,
        'piano': piano,
        'condition_field_list': CONDITION_FIELD_LIST,
        'condition_fields_with_values': condition_fields_with_values,
    })


# ── Slice 9: Maintenance Templates ──────────────────────────────

@login_required
def template_list(request):
    templates = ScheduleTemplate.objects.all()
    return render(request, 'maintenance/template_list.html', {
        'active_nav': 'schedule',
        'templates': templates,
    })


@login_required
def template_create(request):
    if request.method == 'POST':
        form = ScheduleTemplateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Template created.')
            return redirect('template_list')
    else:
        form = ScheduleTemplateForm()
    return render(request, 'maintenance/template_form.html', {
        'active_nav': 'schedule',
        'form': form,
        'editing': False,
    })


@login_required
def template_edit(request, pk):
    tmpl = get_object_or_404(ScheduleTemplate, pk=pk)
    if request.method == 'POST':
        form = ScheduleTemplateForm(request.POST, instance=tmpl)
        if form.is_valid():
            form.save()
            messages.success(request, 'Template updated.')
            return redirect('template_list')
    else:
        form = ScheduleTemplateForm(instance=tmpl)
    return render(request, 'maintenance/template_form.html', {
        'active_nav': 'schedule',
        'form': form,
        'editing': True,
        'template_obj': tmpl,
    })


@login_required
def template_apply(request, pk):
    tmpl = get_object_or_404(ScheduleTemplate, pk=pk)
    pianos = Piano.objects.filter(is_active=True).select_related('venue')

    if request.method == 'POST':
        piano_ids = request.POST.getlist('pianos')
        created = 0
        for pid in piano_ids:
            piano = Piano.objects.get(pk=pid)
            MaintenanceSchedule.objects.create(
                piano=piano,
                template=tmpl,
                task_name=tmpl.task_name,
                task_type=tmpl.task_type,
                interval_days=tmpl.interval_days,
                warning_days_before=tmpl.warning_days_before,
                is_active=True,
            )
            created += 1
        messages.success(request, f'Template applied to {created} piano(s).')
        return redirect('template_list')

    return render(request, 'maintenance/template_apply.html', {
        'active_nav': 'schedule',
        'template_obj': tmpl,
        'pianos': pianos,
    })


@login_required
def schedule_toggle(request, pk):
    sched = get_object_or_404(MaintenanceSchedule, pk=pk)
    if request.method == 'POST':
        sched.is_active = not sched.is_active
        sched.save()
        state = 'resumed' if sched.is_active else 'paused'
        messages.success(request, f'Schedule "{sched.task_name}" {state}.')
    return redirect('piano_detail', pk=sched.piano_id)


@login_required
def schedule_delete(request, pk):
    sched = get_object_or_404(MaintenanceSchedule, pk=pk)
    piano_pk = sched.piano_id
    if request.method == 'POST':
        sched.delete()
        messages.success(request, 'Schedule removed.')
    return redirect('piano_detail', pk=piano_pk)


# ── Slice 10: Technicians ───────────────────────────────────────

@login_required
def technician_list(request):
    techs = Technician.objects.filter(is_active=True).order_by('first_name', 'last_name')
    return render(request, 'maintenance/technician_list.html', {
        'active_nav': 'technicians',
        'technicians': techs,
    })


# ── Slice 10: Parts ─────────────────────────────────────────────

@login_required
def part_list(request):
    parts = Part.objects.all()
    return render(request, 'maintenance/part_list.html', {
        'active_nav': 'parts',
        'parts': parts,
    })


@login_required
def part_create(request):
    if request.method == 'POST':
        form = PartForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Part added.')
            return redirect('part_list')
    else:
        form = PartForm()
    return render(request, 'maintenance/part_form.html', {
        'active_nav': 'parts',
        'form': form,
        'editing': False,
    })


@login_required
def part_edit(request, pk):
    part = get_object_or_404(Part, pk=pk)
    if request.method == 'POST':
        form = PartForm(request.POST, instance=part)
        if form.is_valid():
            form.save()
            messages.success(request, 'Part updated.')
            return redirect('part_list')
    else:
        form = PartForm(instance=part)
    return render(request, 'maintenance/part_form.html', {
        'active_nav': 'parts',
        'form': form,
        'editing': True,
        'part': part,
    })


# ── Slice 10: CSV Import ────────────────────────────────────────

@login_required
def piano_import_csv(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        decoded = csv_file.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(decoded))
        created = 0
        errors = []
        for i, row in enumerate(reader, start=2):
            try:
                org_name = row.get('organization', '').strip()
                venue_name = row.get('venue', '').strip()
                org, _ = Organization.objects.get_or_create(name=org_name) if org_name else (None, False)
                if not org:
                    org = Organization.objects.first()
                    if not org:
                        org = Organization.objects.create(name='Default Organization')
                venue, _ = Venue.objects.get_or_create(
                    name=venue_name,
                    defaults={'organization': org},
                )
                Piano.objects.create(
                    name=row.get('name', '').strip(),
                    make=row.get('make', '').strip(),
                    model=row.get('model', '').strip(),
                    serial_number=row.get('serial_number', '').strip(),
                    piano_type=row.get('piano_type', 'Grand').strip(),
                    venue=venue,
                    section=row.get('section', '').strip(),
                    room=row.get('room', '').strip(),
                    year_built=int(row['year_built']) if row.get('year_built', '').strip() else None,
                    year_acquired=int(row['year_acquired']) if row.get('year_acquired', '').strip() else None,
                    notes=row.get('notes', '').strip(),
                )
                created += 1
            except Exception as e:
                errors.append(f'Row {i}: {e}')

        if created:
            messages.success(request, f'{created} piano(s) imported.')
        if errors:
            messages.warning(request, f'{len(errors)} row(s) skipped. First error: {errors[0]}')
        return redirect('piano_list')

    return render(request, 'maintenance/piano_import.html', {
        'active_nav': 'pianos',
    })


# ── Slice 10: QR Codes ──────────────────────────────────────────

@login_required
def qr_codes(request):
    pianos = Piano.objects.filter(is_active=True).select_related('venue').order_by('venue__name', 'name')
    base_url = request.build_absolute_uri('/maintenance_request/')
    piano_qrs = []
    for p in pianos:
        piano_qrs.append({
            'piano': p,
            'url': f'{base_url}{p.qr_code_token}/',
        })
    return render(request, 'maintenance/qr_codes.html', {
        'active_nav': 'pianos',
        'piano_qrs': piano_qrs,
    })


# ── Slice 10: Reports ───────────────────────────────────────────

@login_required
def reports(request):
    return render(request, 'maintenance/reports.html', {
        'active_nav': 'dashboard',
    })


@login_required
def report_export_workorders(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="work_orders.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'Piano', 'Venue', 'Type', 'Status', 'Priority',
                     'Assigned To', 'Due Date', 'Completed', 'Created', 'Description'])
    wos = WorkOrder.objects.select_related('piano', 'piano__venue', 'assigned_tech').order_by('-created_at')
    for wo in wos:
        writer.writerow([
            f'WO-{wo.pk}',
            wo.piano.name,
            wo.piano.venue.name,
            wo.order_type,
            wo.status,
            wo.priority,
            wo.assigned_tech.get_full_name() if wo.assigned_tech else '',
            wo.due_date or '',
            wo.completed_date or '',
            wo.created_at.strftime('%Y-%m-%d'),
            wo.description,
        ])
    return response


@login_required
def report_export_pianos(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="pianos.csv"'
    writer = csv.writer(response)
    writer.writerow(['Name', 'Make', 'Model', 'Serial Number', 'Type',
                     'Venue', 'Section', 'Room', 'Year Built', 'Year Acquired', 'Notes'])
    pianos = Piano.objects.filter(is_active=True).select_related('venue').order_by('name')
    for p in pianos:
        writer.writerow([
            p.name, p.make, p.model, p.serial_number, p.piano_type,
            p.venue.name, p.section, p.room, p.year_built or '',
            p.year_acquired or '', p.notes,
        ])
    return response


# ── Service Visits ───────────────────────────────────────────────

@login_required
def service_visit_list(request):
    qs = (
        ServiceVisit.objects
        .select_related('venue', 'venue__organization', 'technician')
        .order_by('-date', '-created_at')
    )

    venue_filter = request.GET.get('venue', '')
    tech_filter = request.GET.get('technician', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if venue_filter:
        qs = qs.filter(venue_id=venue_filter)
    if tech_filter:
        qs = qs.filter(technician_id=tech_filter)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    return render(request, 'maintenance/service_visit_list.html', {
        'active_nav': 'visits',
        'visits': qs,
        'venues': Venue.objects.all(),
        'technicians': Technician.objects.filter(is_active=True).order_by('first_name', 'last_name'),
        'venue_filter': venue_filter,
        'tech_filter': tech_filter,
        'date_from': date_from,
        'date_to': date_to,
    })


@login_required
def service_visit_detail(request, pk):
    visit = get_object_or_404(
        ServiceVisit.objects.select_related('venue', 'venue__organization', 'technician'),
        pk=pk,
    )
    linked_wos = visit.work_orders.select_related('piano', 'assigned_tech').order_by('-created_at')
    available_wos = (
        WorkOrder.objects
        .filter(
            piano__venue=visit.venue,
            status__in=[WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS],
            service_visit__isnull=True,
        )
        .select_related('piano', 'assigned_tech')
        .order_by('-created_at')
    )
    return render(request, 'maintenance/service_visit_detail.html', {
        'active_nav': 'visits',
        'visit': visit,
        'linked_wos': linked_wos,
        'available_wos': available_wos,
    })


@login_required
def service_visit_create(request):
    if request.method == 'POST':
        form = ServiceVisitForm(request.POST)
        if form.is_valid():
            visit = form.save()
            messages.success(request, f'Service visit planned for {visit.date}.')
            return redirect('service_visit_detail', pk=visit.pk)
    else:
        form = ServiceVisitForm()

    return render(request, 'maintenance/service_visit_form.html', {
        'active_nav': 'visits',
        'form': form,
        'venues': Venue.objects.all(),
        'technicians': Technician.objects.filter(is_active=True).order_by('first_name', 'last_name'),
        'visit': None,
    })


@login_required
def service_visit_complete(request, pk):
    visit = get_object_or_404(
        ServiceVisit.objects.select_related('venue', 'technician'),
        pk=pk,
    )
    if request.method == 'POST':
        form = ServiceVisitCompleteForm(request.POST)
        if form.is_valid():
            if form.cleaned_data.get('time_in'):
                visit.time_in = form.cleaned_data['time_in']
            if form.cleaned_data.get('time_out'):
                visit.time_out = form.cleaned_data['time_out']
            if form.cleaned_data.get('miles_driven') is not None:
                visit.miles_driven = form.cleaned_data['miles_driven']
            if form.cleaned_data.get('notes'):
                visit.notes = form.cleaned_data['notes']
            visit.status = ServiceVisit.VisitStatus.COMPLETE
            visit.save()
            messages.success(request, f'Service visit on {visit.date} marked complete.')
            return redirect('service_visit_detail', pk=visit.pk)
    else:
        form = ServiceVisitCompleteForm(initial={
            'time_in': visit.time_in,
            'time_out': visit.time_out,
            'miles_driven': visit.miles_driven,
            'notes': visit.notes,
        })

    return render(request, 'maintenance/service_visit_complete.html', {
        'active_nav': 'visits',
        'visit': visit,
        'form': form,
    })


@login_required
def service_visit_add_workorder(request, pk):
    visit = get_object_or_404(ServiceVisit, pk=pk)
    if request.method == 'POST':
        wo_id = request.POST.get('work_order_id')
        if wo_id:
            try:
                wo = WorkOrder.objects.get(pk=int(wo_id))
                wo.service_visit = visit
                wo.save(update_fields=['service_visit'])
                messages.success(request, f'WO-{wo.pk} linked to this visit.')
            except (WorkOrder.DoesNotExist, ValueError):
                messages.error(request, 'Work order not found.')
    return redirect('service_visit_detail', pk=visit.pk)
