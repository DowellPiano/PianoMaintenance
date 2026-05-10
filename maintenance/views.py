import csv
import io
from datetime import date, timedelta
from decimal import Decimal
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q, Count, Sum, Max, DecimalField
from django.db.models.functions import Coalesce
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib import messages

from .models import (
    Organization, Venue, Piano, WorkOrder, MaintenanceRequest,
    MaintenanceSchedule, ScheduleTemplate, ConditionReading,
    Technician, Part, PartUsed, MaintenanceLog, TaskType, Photo, Tag,
    CompanySettings,
)
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from .forms import (
    OrganizationForm, VenueForm, PianoForm, WorkOrderForm, WorkOrderCompleteForm,
    WorkOrderLogWorkForm, ConditionReadingForm, ScheduleTemplateForm, PartForm,
    SignUpForm, CompanySettingsForm, UserProfileForm, TechnicianCreateForm,
    TechnicianUpdateForm,
)


# ── Role-based access ────────────────────────────────────────────

def admin_required(view_func):
    """Decorator: requires login + admin role."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.role_admin:
            messages.error(request, 'Admin access required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def staff_required(view_func):
    """Decorator: requires login + an app role."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.role_admin or request.user.role_technician):
            messages.error(request, 'Technician access required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ── Public (no login) ──────────────────────────────────────────────

def maintenance_request_form(request, token):
    piano = get_object_or_404(Piano, qr_code_token=token)

    if request.user.is_authenticated:
        return redirect('piano_detail', pk=piano.pk)

    if request.method == 'POST':
        # Basic rate limiting: max 5 requests per piano per hour
        one_hour_ago = timezone.now() - timedelta(hours=1)
        recent_count = MaintenanceRequest.objects.filter(
            piano=piano, created_at__gte=one_hour_ago,
        ).count()
        if recent_count >= 5:
            return HttpResponse(
                '<h2>Too many requests.</h2>'
                '<p>Please wait a while before submitting another request for this piano.</p>',
                content_type='text/html', status=429,
            )

        issue = request.POST.get('issue_description', '').strip()[:2000]
        name  = request.POST.get('reported_by_name', '').strip()[:200]
        email = request.POST.get('reported_by_email', '').strip()[:254]
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


def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request,
                f'Account request received for {user.get_short_name() or user.username}. '
                'An admin must activate it before you can sign in.',
            )
            return redirect('signup_pending')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})


def signup_pending(request):
    return render(request, 'registration/signup_pending.html')


# ── Dashboard ──────────────────────────────────────────────────────

@login_required
def dashboard(request):
    today = date.today()
    month_start = today.replace(day=1)
    user = request.user
    is_admin = user.role_admin

    if is_admin:
        # Admin sees everything
        wo_base = WorkOrder.objects
        overdue_count = wo_base.filter(
            status__in=[WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS],
            due_date__lt=today,
        ).count()
        open_wo_count = wo_base.filter(status=WorkOrder.Status.OPEN).count()
        in_progress_count = wo_base.filter(status=WorkOrder.Status.IN_PROGRESS).count()
        pending_request_count = MaintenanceRequest.objects.filter(
            status=MaintenanceRequest.RequestStatus.NEW,
        ).count()
        piano_count = Piano.objects.filter(is_active=True).count()
        venue_count = Venue.objects.count()
        org_count = Organization.objects.count()
        completed_this_month = wo_base.filter(
            status=WorkOrder.Status.COMPLETE,
            completed_date__gte=month_start,
        ).count()
        dashboard_work_orders = (
            wo_base
            .select_related('piano', 'piano__venue')
            .order_by('-created_at')[:10]
        )
    else:
        # Tech-only: show only their own assigned work
        my_wos = WorkOrder.objects.filter(assigned_tech=user)
        overdue_count = my_wos.filter(
            status__in=[WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS],
            due_date__lt=today,
        ).count()
        open_wo_count = my_wos.filter(status=WorkOrder.Status.OPEN).count()
        in_progress_count = my_wos.filter(status=WorkOrder.Status.IN_PROGRESS).count()
        pending_request_count = None
        piano_count = None
        venue_count = None
        org_count = None
        completed_this_month = my_wos.filter(
            status=WorkOrder.Status.COMPLETE,
            completed_date__gte=month_start,
        ).count()
        dashboard_work_orders = (
            my_wos
            .select_related('piano', 'piano__venue')
            .filter(status__in=[WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS])
            .order_by('due_date', '-created_at')
        )

    return render(request, 'maintenance/dashboard.html', {
        'active_nav': 'dashboard',
        'is_admin': is_admin,
        'overdue_count': overdue_count,
        'open_wo_count': open_wo_count,
        'in_progress_count': in_progress_count,
        'pending_request_count': pending_request_count,
        'piano_count': piano_count,
        'venue_count': venue_count,
        'org_count': org_count,
        'completed_this_month': completed_this_month,
        'dashboard_work_orders': dashboard_work_orders,
    })


# ── Pianos ─────────────────────────────────────────────────────────

@login_required
def piano_list(request):
    today = date.today()
    soon = today + timedelta(days=30)

    qs = Piano.objects.filter(is_active=True).select_related('venue', 'venue__organization').prefetch_related('photos', 'tags')

    search_query = request.GET.get('q', '').strip()
    org_filter = request.GET.get('org', '')
    venue_filter = request.GET.get('venue', '')
    type_filter = request.GET.get('type', '')
    tag_filter = request.GET.get('tag', '')

    if search_query:
        qs = qs.filter(
            Q(name__icontains=search_query) |
            Q(make__icontains=search_query) |
            Q(serial_number__icontains=search_query) |
            Q(tags__name__icontains=search_query)
        ).distinct()
    if org_filter:
        qs = qs.filter(venue__organization_id=org_filter)
    if venue_filter:
        qs = qs.filter(venue_id=venue_filter)
    if type_filter:
        qs = qs.filter(piano_type=type_filter)
    if tag_filter:
        qs = qs.filter(tags__id=tag_filter)

    return render(request, 'maintenance/piano_list.html', {
        'active_nav': 'pianos',
        'pianos': qs,
        'organizations': Organization.objects.all(),
        'venues': Venue.objects.all(),
        'tags': Tag.objects.all(),
        'search_query': search_query,
        'org_filter': org_filter,
        'venue_filter': venue_filter,
        'type_filter': type_filter,
        'tag_filter': tag_filter,
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
    piano = get_object_or_404(Piano.objects.select_related('venue').prefetch_related('tags'), pk=pk)
    ctx = _piano_context(piano)
    ctx['qr_url'] = request.build_absolute_uri(f'/maintenance_request/{piano.qr_code_token}/')
    ctx['photos'] = piano.photos.all()
    ctx['piano_tags'] = piano.tags.all()
    ctx['available_tags'] = Tag.objects.filter(pianos__is_active=True).exclude(pk__in=piano.tags.all()).distinct()
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


@admin_required
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


@admin_required
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


@admin_required
def piano_deactivate(request, pk):
    piano = get_object_or_404(Piano, pk=pk)
    if request.method == 'POST':
        piano.is_active = False
        piano.save(update_fields=['is_active'])
        messages.success(request, f'Piano "{piano.name}" has been deactivated.')
        return redirect('piano_list')
    return render(request, 'maintenance/piano_confirm_deactivate.html', {
        'active_nav': 'pianos',
        'piano': piano,
    })


def _piano_tags_context(piano):
    return {
        'piano': piano,
        'piano_tags': piano.tags.all(),
        'available_tags': Tag.objects.filter(pianos__is_active=True).exclude(pk__in=piano.tags.all()).distinct(),
    }


@admin_required
def piano_add_tag(request, pk):
    piano = get_object_or_404(Piano, pk=pk)
    if request.method == 'POST':
        tag_name = request.POST.get('tag_name', '').strip()
        if tag_name:
            tag, _ = Tag.objects.get_or_create(name=tag_name)
            piano.tags.add(tag)
    if request.headers.get('HX-Request'):
        return render(request, 'maintenance/partials/piano_tags.html', _piano_tags_context(piano))
    return redirect('piano_detail', pk=piano.pk)


@admin_required
def piano_remove_tag(request, pk, tag_pk):
    piano = get_object_or_404(Piano, pk=pk)
    if request.method == 'POST':
        piano.tags.remove(tag_pk)
        if not Tag.objects.filter(pk=tag_pk, pianos__is_active=True).exists():
            Tag.objects.filter(pk=tag_pk).delete()
    if request.headers.get('HX-Request'):
        return render(request, 'maintenance/partials/piano_tags.html', _piano_tags_context(piano))
    return redirect('piano_detail', pk=piano.pk)


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


@admin_required
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


@admin_required
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


@admin_required
def organization_delete(request, pk):
    organization = get_object_or_404(Organization, pk=pk)
    venue_count = organization.venues.count()

    if request.method == 'POST':
        name = organization.name
        organization.delete()  # venues SET_NULL'd, keep existing
        messages.success(request, f'Organization "{name}" deleted.')
        return redirect('organization_list')

    return render(request, 'maintenance/organization_confirm_delete.html', {
        'active_nav': 'organizations',
        'organization': organization,
        'venue_count': venue_count,
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


@admin_required
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


@admin_required
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


@admin_required
def venue_delete(request, pk):
    venue = get_object_or_404(Venue.objects.select_related('organization'), pk=pk)
    piano_count = Piano.objects.filter(venue=venue).count()

    if request.method == 'POST':
        name = venue.name
        org_pk = venue.organization_id
        venue.delete()  # stamps venue_display on pianos, then SET_NULL
        messages.success(request, f'Venue "{name}" deleted.')
        if org_pk:
            return redirect('organization_detail', pk=org_pk)
        return redirect('venue_list')

    return render(request, 'maintenance/venue_confirm_delete.html', {
        'active_nav': 'venues',
        'venue': venue,
        'piano_count': piano_count,
    })


# ── Work Orders ───────────────────────────────────────────────────

@login_required
def workorder_list(request):
    _generate_scheduled_work_orders()
    today = date.today()
    qs = WorkOrder.objects.select_related('piano', 'piano__venue', 'assigned_tech')

    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    type_filter = request.GET.get('type', '')
    org_filter = request.GET.get('org', '')
    venue_filter = request.GET.get('venue', '')
    sort_key = request.GET.get('sort', 'created')
    sort_dir = request.GET.get('dir', 'desc')

    sort_options = {
        'id': ('pk',),
        'piano': ('piano__name', 'piano_display', 'pk'),
        'type': ('order_type', 'pk'),
        'status': ('status', 'pk'),
        'priority': ('priority', 'pk'),
        'assigned': (
            'assigned_tech__last_name',
            'assigned_tech__first_name',
            'assigned_tech__username',
            'pk',
        ),
        'due': ('due_date', 'pk'),
        'created': ('created_at', 'pk'),
    }
    if sort_key not in sort_options:
        sort_key = 'created'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'desc'

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
    if org_filter:
        qs = qs.filter(piano__venue__organization_id=org_filter)
    if venue_filter:
        qs = qs.filter(piano__venue_id=venue_filter)

    order_fields = sort_options[sort_key]
    if sort_dir == 'desc':
        order_fields = tuple(f'-{field}' for field in order_fields)
    qs = qs.order_by(*order_fields)

    sort_columns = []
    for key, label in [
        ('id', 'ID'),
        ('piano', 'Piano'),
        ('type', 'Type'),
        ('status', 'Status'),
        ('priority', 'Priority'),
        ('assigned', 'Assigned To'),
        ('due', 'Due'),
        ('created', 'Created'),
    ]:
        params = request.GET.copy()
        params['sort'] = key
        params['dir'] = 'desc' if sort_key == key and sort_dir == 'asc' else 'asc'
        sort_columns.append({
            'key': key,
            'label': label,
            'url': f'?{params.urlencode()}',
            'active': sort_key == key,
        })

    context = {
        'active_nav': 'workorders',
        'work_orders': qs,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        'sort_columns': sort_columns,
        'search_query': search_query,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'type_filter': type_filter,
        'org_filter': org_filter,
        'venue_filter': venue_filter,
        'organizations': Organization.objects.all(),
        'venues': Venue.objects.all(),
        'status_choices': WorkOrder.Status.choices,
        'priority_choices': WorkOrder.Priority.choices,
        'type_choices': WorkOrder.OrderType.choices,
        'today': today,
    }

    if request.headers.get('HX-Request') == 'true':
        return render(request, 'maintenance/partials/workorder_table.html', context)
    return render(request, 'maintenance/workorder_list.html', context)


@login_required
def workorder_detail(request, pk):
    wo = get_object_or_404(
        WorkOrder.objects.select_related('piano', 'piano__venue', 'assigned_tech'),
        pk=pk,
    )
    user = request.user
    logs = wo.logs.select_related('technician').order_by('-logged_at')
    technicians = Technician.objects.filter(
        is_active=True, role_technician=True,
    ).order_by('first_name', 'last_name')

    is_assigned_to_me = wo.assigned_tech_id == user.pk
    can_edit_wo = user.role_admin or (user.role_technician and is_assigned_to_me)

    return render(request, 'maintenance/workorder_detail.html', {
        'active_nav': 'workorders',
        'wo': wo,
        'logs': logs,
        'technicians': technicians,
        'today': date.today(),
        'can_edit_wo': can_edit_wo,
        'is_assigned_to_me': is_assigned_to_me,
    })


@admin_required
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
        'technicians': Technician.objects.filter(is_active=True, role_technician=True),
        'type_choices': WorkOrder.OrderType.choices,
        'task_type_choices': TaskType.choices,
        'status_choices': WorkOrder.Status.choices,
        'priority_choices': WorkOrder.Priority.choices,
    })


@login_required
def workorder_assign(request, pk):
    wo = get_object_or_404(WorkOrder, pk=pk)
    user = request.user

    if request.method == 'POST':
        if user.role_admin:
            # Admin can assign any technician
            tech_id = request.POST.get('assigned_tech')
            if tech_id:
                try:
                    wo.assigned_tech_id = int(tech_id)
                except (ValueError, TypeError):
                    pass
            else:
                wo.assigned_tech = None
        elif user.role_technician:
            # Tech can only assign self to unassigned WOs
            action = request.POST.get('assign_action')
            if action == 'assign_self' and wo.assigned_tech is None:
                wo.assigned_tech = user

        if wo.status == WorkOrder.Status.OPEN and wo.assigned_tech_id:
            wo.status = WorkOrder.Status.IN_PROGRESS
        wo.save()

    technicians = Technician.objects.filter(
        is_active=True, role_technician=True,
    ).order_by('first_name', 'last_name')
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
    user = request.user
    if not user.role_admin and wo.assigned_tech_id != user.pk:
        messages.error(request, 'You can only complete work orders assigned to you.')
        return redirect('workorder_detail', pk=wo.pk)

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

            # Handle photo uploads (validate type and size)
            for f in request.FILES.getlist('photos'):
                if _validate_upload(f) is None:
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


@admin_required
def workorder_delete(request, pk):
    wo = get_object_or_404(
        WorkOrder.objects.select_related('piano', 'piano__venue'),
        pk=pk,
    )
    log_count = wo.logs.count()

    if request.method == 'POST':
        wo_id = wo.pk
        wo.delete()
        messages.success(request, f'Work Order WO-{wo_id} deleted.')
        return redirect('workorder_list')

    return render(request, 'maintenance/workorder_confirm_delete.html', {
        'active_nav': 'workorders',
        'wo': wo,
        'log_count': log_count,
    })


@login_required
def workorder_log_work(request, pk):
    """Log work against a work order without completing it."""
    wo = get_object_or_404(
        WorkOrder.objects.select_related('piano', 'piano__venue', 'assigned_tech'),
        pk=pk,
    )
    user = request.user
    if not user.role_admin and wo.assigned_tech_id != user.pk:
        messages.error(request, 'You can only log work on work orders assigned to you.')
        return redirect('workorder_detail', pk=wo.pk)

    parts = Part.objects.all().order_by('name')

    if request.method == 'POST':
        form = WorkOrderLogWorkForm(request.POST)
        if form.is_valid():
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
                if _validate_upload(f) is None:
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

            # Move to In Progress if still Open
            if wo.status == WorkOrder.Status.OPEN:
                wo.status = WorkOrder.Status.IN_PROGRESS
                wo.save(update_fields=['status'])

            messages.success(request, f'Work logged for WO-{wo.pk}.')
            return redirect('workorder_detail', pk=wo.pk)
    else:
        form = WorkOrderLogWorkForm()

    return render(request, 'maintenance/workorder_log_work.html', {
        'active_nav': 'workorders',
        'wo': wo,
        'form': form,
        'parts': parts,
    })


# ── Photo Upload ─────────────────────────────────────────────────

ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


def _validate_upload(f):
    """Return an error string if the file is not a valid image, else None."""
    if f.size > MAX_UPLOAD_SIZE:
        return f'{f.name}: file too large ({f.size / 1024 / 1024:.1f} MB, max 10 MB)'
    if f.content_type not in ALLOWED_IMAGE_TYPES:
        return f'{f.name}: unsupported file type ({f.content_type})'
    return None


@login_required
def piano_photo_upload(request, pk):
    piano = get_object_or_404(Piano, pk=pk)
    if request.method == 'POST':
        caption = request.POST.get('caption', '')
        files = request.FILES.getlist('photos')
        uploaded = 0
        for f in files:
            err = _validate_upload(f)
            if err:
                messages.error(request, err)
                continue
            is_profile = not piano.photos.exists() and uploaded == 0
            Photo.objects.create(piano=piano, image=f, caption=caption, is_profile_photo=is_profile)
            uploaded += 1
        if uploaded:
            messages.success(request, f'{uploaded} photo(s) uploaded.')
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


@staff_required
def piano_photo_delete(request, pk, photo_pk):
    piano = get_object_or_404(Piano, pk=pk)
    photo = get_object_or_404(Photo, pk=photo_pk, piano=piano)

    if request.method == 'POST':
        was_profile = photo.is_profile_photo
        if photo.image:
            photo.image.delete(save=False)
        photo.delete()

        if was_profile:
            next_photo = piano.photos.order_by('-uploaded_at').first()
            if next_photo:
                next_photo.is_profile_photo = True
                next_photo.save(update_fields=['is_profile_photo'])

        messages.success(request, 'Photo deleted.')
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


@admin_required
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


@admin_required
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

@admin_required
def template_list(request):
    templates = ScheduleTemplate.objects.all()
    return render(request, 'maintenance/template_list.html', {
        'active_nav': 'schedule',
        'templates': templates,
    })


@admin_required
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


@admin_required
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


@admin_required
def template_apply(request, pk):
    tmpl = get_object_or_404(ScheduleTemplate, pk=pk)
    pianos = Piano.objects.filter(is_active=True).select_related('venue')

    if request.method == 'POST':
        piano_ids = request.POST.getlist('pianos')
        created = 0
        for pid in piano_ids:
            try:
                piano = Piano.objects.get(pk=int(pid))
            except (Piano.DoesNotExist, ValueError, TypeError):
                continue
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


@admin_required
def schedule_toggle(request, pk):
    sched = get_object_or_404(MaintenanceSchedule, pk=pk)
    if request.method == 'POST':
        sched.is_active = not sched.is_active
        sched.save()
        state = 'resumed' if sched.is_active else 'paused'
        messages.success(request, f'Schedule "{sched.task_name}" {state}.')
    return redirect('piano_detail', pk=sched.piano_id)


@admin_required
def schedule_delete(request, pk):
    sched = get_object_or_404(MaintenanceSchedule, pk=pk)
    piano_pk = sched.piano_id
    if request.method == 'POST':
        sched.delete()
        messages.success(request, 'Schedule removed.')
    return redirect('piano_detail', pk=piano_pk)


# ── Slice 10: Technicians ───────────────────────────────────────

@admin_required
def technician_list(request):
    techs = (
        Technician.objects
        .annotate(
            open_work_order_count=Count(
                'work_orders',
                filter=Q(work_orders__status__in=[
                    WorkOrder.Status.OPEN,
                    WorkOrder.Status.IN_PROGRESS,
                ]),
            ),
        )
        .order_by('-is_active', 'first_name', 'last_name', 'username')
    )
    return render(request, 'maintenance/technician_list.html', {
        'active_nav': 'technicians',
        'technicians': techs,
    })


@admin_required
def technician_create(request):
    if request.method == 'POST':
        form = TechnicianCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'User {user.username} created.')
            return redirect('technician_list')
    else:
        form = TechnicianCreateForm(initial={
            'is_active': True,
            'role_technician': True,
        })
    return render(request, 'maintenance/technician_form.html', {
        'active_nav': 'technicians',
        'form': form,
        'editing': False,
    })


@admin_required
def technician_edit(request, pk):
    tech = get_object_or_404(Technician, pk=pk)
    if request.method == 'POST':
        form = TechnicianUpdateForm(request.POST, instance=tech)
        if form.is_valid():
            updated = form.save(commit=False)
            if updated.pk == request.user.pk:
                if not updated.is_active:
                    form.add_error('is_active', 'You cannot deactivate your own account.')
                if not updated.role_admin:
                    form.add_error('role_admin', 'You cannot remove your own admin role.')
            if not form.errors:
                updated.save()
                messages.success(request, f'User {updated.username} updated.')
                return redirect('technician_list')
    else:
        form = TechnicianUpdateForm(instance=tech)
    return render(request, 'maintenance/technician_form.html', {
        'active_nav': 'technicians',
        'form': form,
        'editing': True,
        'technician': tech,
    })


@admin_required
def technician_report(request):
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    log_q = Q()
    if date_from:
        log_q &= Q(logs__logged_at__date__gte=date_from)
    if date_to:
        log_q &= Q(logs__logged_at__date__lte=date_to)

    techs = (
        Technician.objects
        .filter(is_active=True)
        .annotate(
            total_hours=Coalesce(
                Sum('logs__hours_worked', filter=log_q),
                Decimal('0'),
                output_field=DecimalField(),
            ),
            wo_count=Count(
                'logs__work_order',
                distinct=True,
                filter=log_q,
            ),
            last_activity=Max(
                'logs__logged_at',
                filter=log_q,
            ),
        )
        .order_by('last_name', 'first_name')
    )

    techs_list = list(techs)
    total_hours = sum(t.total_hours for t in techs_list)
    total_wos = sum(t.wo_count for t in techs_list)

    return render(request, 'maintenance/technician_report.html', {
        'active_nav': 'technicians',
        'technicians': techs_list,
        'total_hours': total_hours,
        'total_wos': total_wos,
        'date_from': date_from,
        'date_to': date_to,
    })


@admin_required
def technician_report_csv(request):
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    log_q = Q()
    if date_from:
        log_q &= Q(logs__logged_at__date__gte=date_from)
    if date_to:
        log_q &= Q(logs__logged_at__date__lte=date_to)

    techs = (
        Technician.objects
        .filter(is_active=True)
        .annotate(
            total_hours=Coalesce(
                Sum('logs__hours_worked', filter=log_q),
                Decimal('0'),
                output_field=DecimalField(),
            ),
            wo_count=Count(
                'logs__work_order',
                distinct=True,
                filter=log_q,
            ),
            last_activity=Max(
                'logs__logged_at',
                filter=log_q,
            ),
        )
        .order_by('last_name', 'first_name')
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="technician_report.csv"'
    writer = csv.writer(response)
    writer.writerow(['Technician', 'Email', 'Total Hours', 'Work Orders Completed', 'Last Activity'])
    for t in techs:
        writer.writerow([
            t.get_full_name() or t.username,
            t.email or '',
            float(t.total_hours),
            t.wo_count,
            t.last_activity.strftime('%Y-%m-%d %H:%M') if t.last_activity else '',
        ])
    return response


# ── Slice 10: Parts ─────────────────────────────────────────────

@admin_required
def part_list(request):
    parts = Part.objects.all()
    return render(request, 'maintenance/part_list.html', {
        'active_nav': 'parts',
        'parts': parts,
    })


@admin_required
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


@admin_required
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

@admin_required
def piano_import_sample_csv(request):
    """Return a sample CSV file the user can fill in and re-upload."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="piano_import_sample.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'name', 'make', 'model', 'serial_number', 'piano_type',
        'organization', 'venue', 'section', 'room',
        'year_built', 'year_acquired', 'notes',
    ])
    writer.writerow([
        'Concert Hall Steinway', 'Steinway & Sons', 'D-274', 'SN-123456', 'Grand',
        'City Symphony Orchestra', 'Main Concert Hall', 'Stage', 'Main Stage',
        '2015', '2016', 'Primary concert instrument',
    ])
    writer.writerow([
        'Practice Room 1', 'Yamaha', 'U3', 'YU3-789012', 'Upright',
        'City Symphony Orchestra', 'Rehearsal Center', 'Floor 2', 'Room 201',
        '2010', '2012', '',
    ])
    return response


@admin_required
def piano_import_csv(request):
    MAX_CSV_SIZE = 5 * 1024 * 1024  # 5 MB
    MAX_CSV_ROWS = 5000

    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        if csv_file.size > MAX_CSV_SIZE:
            messages.error(request, f'CSV file too large ({csv_file.size / 1024 / 1024:.1f} MB, max 5 MB).')
            return redirect('piano_import')
        decoded = csv_file.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(decoded))
        created = 0
        errors = []
        for i, row in enumerate(reader, start=2):
            if i - 2 >= MAX_CSV_ROWS:
                errors.append(f'Stopped after {MAX_CSV_ROWS} rows (limit reached).')
                break
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

@admin_required
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


@admin_required
def qr_codes_csv(request):
    pianos = Piano.objects.filter(is_active=True).select_related('venue').order_by('venue__name', 'name')
    base_url = request.build_absolute_uri('/maintenance_request/')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="piano_qr_labels.csv"'
    writer = csv.writer(response)
    writer.writerow(['Piano Name', 'Make', 'Model', 'Serial Number', 'Venue', 'Section', 'Room', 'QR Code URL'])
    for p in pianos:
        writer.writerow([
            p.name,
            p.make,
            p.model,
            p.serial_number,
            p.venue_name,
            p.section,
            p.room,
            f'{base_url}{p.qr_code_token}/',
        ])
    return response


# ── Slice 10: Reports ───────────────────────────────────────────

@admin_required
def reports(request):
    return render(request, 'maintenance/reports.html', {
        'active_nav': 'dashboard',
    })


@admin_required
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


@admin_required
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


# ── Settings ──────────────────────────────────────────────────────

@login_required
def settings_page(request):
    is_admin = request.user.role_admin
    company = CompanySettings.load() if is_admin else None
    company_form = CompanySettingsForm(instance=company, prefix='company') if is_admin else None
    profile_form = UserProfileForm(instance=request.user, prefix='profile')
    password_form = PasswordChangeForm(user=request.user, prefix='password')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'company' and is_admin:
            company_form = CompanySettingsForm(
                request.POST, instance=company, prefix='company',
            )
            if company_form.is_valid():
                company_form.save()
                messages.success(request, 'Company settings saved.')
                return redirect('settings')

        elif action == 'profile':
            profile_form = UserProfileForm(
                request.POST, instance=request.user, prefix='profile',
            )
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Profile updated.')
                return redirect('settings')

        elif action == 'password':
            password_form = PasswordChangeForm(
                user=request.user, data=request.POST, prefix='password',
            )
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Password changed.')
                return redirect('settings')

    return render(request, 'maintenance/settings.html', {
        'active_nav': 'settings',
        'company_form': company_form,
        'profile_form': profile_form,
        'password_form': password_form,
    })
