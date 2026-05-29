import csv
import io
import mimetypes
import uuid
from datetime import date, timedelta
from decimal import Decimal
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.mail import send_mail
from django.core.files.storage import FileSystemStorage
from django.db.models import Q, Count, Sum, Max, DecimalField
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .audit import log_audit_event, target_audit_events
from .forms import (
    OrganizationForm, VenueForm, PianoForm, WorkOrderForm, WorkOrderCompleteForm,
    WorkOrderLogWorkForm, ConditionReadingForm, ScheduleTemplateForm, PartForm,
    SignUpForm, CompanySettingsForm, UserProfileForm, TechnicianCreateForm,
    TechnicianUpdateForm, CompanyInvitationForm, CompanySwitcherForm,
    BulkPianoIntervalForm,
)
from .email_notifications import (
    notify_maintenance_request,
    notify_work_order_assigned,
)
from .models import (
    Company, CompanyInvitation, CompanyMembership,
    Organization, Venue, Piano, WorkOrder, MaintenanceRequest,
    MaintenanceSchedule, ScheduleTemplate, ConditionReading,
    Technician, Part, PartUsed, MaintenanceLog, TaskType, Photo, Tag,
    CompanySettings,
)
from .tenancy import ACTIVE_COMPANY_SESSION_KEY, company_queryset, company_users, ensure_company_access
from .services import build_company_setup_progress


def _safe_return_url(request, fallback):
    """Return a same-site URL to preserve list/schedule state between pages."""
    return_url = request.GET.get('return_url') or request.POST.get('return_url')
    if return_url and url_has_allowed_host_and_scheme(
        return_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return return_url
    return fallback


def _workorder_detail_url(wo, return_url=None):
    url = f'/work-orders/{wo.pk}/'
    if return_url:
        url = f'{url}?{urlencode({"return_url": return_url})}'
    return url


def _piano_detail_url(piano, return_url=None):
    url = f'/pianos/{piano.pk}/'
    if return_url:
        url = f'{url}?{urlencode({"return_url": return_url})}'
    return url


def _filtered_piano_queryset(request):
    company = ensure_company_access(request)
    qs = Piano.objects.filter(company=company, is_active=True).select_related(
        'venue', 'venue__organization',
    ).prefetch_related('photos', 'tags')

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
            Q(section__icontains=search_query) |
            Q(room__icontains=search_query) |
            Q(room_description__icontains=search_query) |
            Q(room_access_notes__icontains=search_query) |
            Q(tags__name__icontains=search_query)
        ).distinct()
    if org_filter:
        qs = qs.filter(venue__organization_id=org_filter)
    if venue_filter:
        qs = qs.filter(venue_id=venue_filter)
    if type_filter:
        qs = qs.filter(piano_type=type_filter)
    if tag_filter:
        if tag_filter == 'none':
            qs = qs.filter(tags__isnull=True)
        else:
            qs = qs.filter(tags__id=tag_filter)

    return qs, {
        'search_query': search_query,
        'org_filter': org_filter,
        'venue_filter': venue_filter,
        'type_filter': type_filter,
        'tag_filter': tag_filter,
    }


def _service_status_context(wo, today):
    if not wo.piano_id or wo.task_type in ('', TaskType.OTHER):
        return None

    interval_fields = {
        TaskType.TUNING: ('tuning_interval_value', 'tuning_interval_unit'),
        TaskType.REGULATION: ('regulation_interval_value', 'regulation_interval_unit'),
        TaskType.VOICING: ('voicing_interval_value', 'voicing_interval_unit'),
        TaskType.CLEANING: ('cleaning_interval_value', 'cleaning_interval_unit'),
    }
    interval_days = None
    if wo.schedule_id:
        interval_days = wo.schedule.interval_days
    else:
        fields = interval_fields.get(wo.task_type)
        if fields:
            value_field, unit_field = fields
            interval_days = wo.piano._interval_to_days(
                getattr(wo.piano, value_field),
                getattr(wo.piano, unit_field),
            )

    completed_work = WorkOrder.objects.filter(
        company=wo.company,
        piano=wo.piano,
        task_type=wo.task_type,
        status=WorkOrder.Status.COMPLETE,
        completed_date__isnull=False,
    )
    if wo.schedule_id:
        completed_work = completed_work.filter(schedule=wo.schedule)

    last_work_order = completed_work.order_by('-completed_date').first()
    if wo.status == WorkOrder.Status.COMPLETE and wo.completed_date:
        last_service_date = wo.completed_date
    elif last_work_order:
        last_service_date = last_work_order.completed_date
    else:
        last_service_date = None

    if not last_service_date or interval_days is None:
        return {
            'task_type': wo.task_type,
            'last_service_date': last_service_date,
            'has_interval': interval_days is not None,
            'days_from_due': None,
            'display_days': None,
            'timing_label': None,
        }

    elapsed_days = (today - last_service_date).days
    days_from_due = interval_days - elapsed_days
    if days_from_due > 0:
        timing_label = 'early'
    elif days_from_due < 0:
        timing_label = 'late'
    else:
        timing_label = 'due today'

    return {
        'task_type': wo.task_type,
        'last_service_date': last_service_date,
        'has_interval': True,
        'days_from_due': days_from_due,
        'display_days': abs(days_from_due),
        'timing_label': timing_label,
    }


def _is_tech_mode(request):
    membership = getattr(request, 'active_membership', None)
    return bool(
        request.user.is_authenticated
        and membership
        and membership.is_active
        and membership.role_admin
        and membership.role_technician
        and request.session.get('tech_mode')
    )


def _can_update_workorder(user, wo, tech_mode=False):
    return (user.has_company_role(wo.company, admin=True) and not tech_mode) or (
        user.has_company_role(wo.company, technician=True)
        and (wo.assigned_tech_id == user.pk or wo.assigned_tech_id is None)
    )


def _filtered_workorders(request):
    company = ensure_company_access(request)
    qs = WorkOrder.objects.filter(company=company).select_related('piano', 'piano__venue', 'assigned_tech')
    tech_mode = _is_tech_mode(request)

    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    type_filter = request.GET.get('type', '')
    task_type_filter = request.GET.get('task_type', type_filter)
    org_filter = request.GET.get('org', '')
    venue_filter = request.GET.get('venue', '')
    completed_from = request.GET.get('completed_from', '')
    completed_to = request.GET.get('completed_to', '')
    sort_key = request.GET.get('sort', 'created')
    sort_dir = request.GET.get('dir', 'desc')

    sort_options = {
        'id': ('pk',),
        'piano': ('piano__name', 'piano_display', 'pk'),
        'type': ('task_type', 'order_type', 'pk'),
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
        'completed': ('completed_date', 'pk'),
    }
    if sort_key not in sort_options:
        sort_key = 'created'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'desc'

    if tech_mode:
        qs = qs.filter(Q(assigned_tech=request.user) | Q(assigned_tech__isnull=True))
        if not status_filter and not completed_from and not completed_to:
            qs = qs.filter(status__in=[WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS])

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
    if task_type_filter:
        qs = qs.filter(task_type=task_type_filter)
    if org_filter:
        qs = qs.filter(piano__venue__organization_id=org_filter)
    if venue_filter:
        qs = qs.filter(piano__venue_id=venue_filter)
    if completed_from:
        qs = qs.filter(completed_date__gte=completed_from)
    if completed_to:
        qs = qs.filter(completed_date__lte=completed_to)

    order_fields = sort_options[sort_key]
    if sort_dir == 'desc':
        order_fields = tuple(f'-{field}' for field in order_fields)
    qs = qs.order_by(*order_fields)

    return qs, {
        'search_query': search_query,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'type_filter': task_type_filter,
        'org_filter': org_filter,
        'venue_filter': venue_filter,
        'completed_from': completed_from,
        'completed_to': completed_to,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        'sort_options': sort_options,
    }


def _user_is_company_admin(request):
    return bool(request.active_membership and request.active_membership.role_admin)


def _user_is_company_technician(request):
    return bool(request.active_membership and request.active_membership.role_technician)


def _company_organizations(request):
    return Organization.objects.filter(company=ensure_company_access(request))


def _company_venues(request):
    return Venue.objects.filter(company=ensure_company_access(request))


def _company_pianos(request):
    return Piano.objects.filter(company=ensure_company_access(request))


def _company_workorders(request):
    return WorkOrder.objects.filter(company=ensure_company_access(request))


def _company_parts(request):
    return Part.objects.filter(company=ensure_company_access(request))


def _company_tags(request):
    return Tag.objects.filter(company=ensure_company_access(request))


def _company_settings(request):
    return CompanySettings.load_for_company(ensure_company_access(request))


SETUP_TASK_URLS = {
    'company_profile': 'settings',
    'team': 'settings',
    'organizations': 'organization_create',
    'venues': 'venue_create',
    'pianos': 'piano_create',
}


def _setup_progress_context(company):
    progress = build_company_setup_progress(company)
    tasks = []
    for task in progress.tasks:
        url_name = SETUP_TASK_URLS.get(task.key)
        tasks.append({
            'key': task.key,
            'title': task.title,
            'detail': task.detail,
            'is_complete': task.is_complete,
            'cta_label': task.cta_label,
            'cta_url': reverse(url_name) if url_name else '',
        })
    return {
        'tasks': tasks,
        'completed_count': progress.completed_count,
        'total_count': progress.total_count,
        'percent_complete': progress.percent_complete,
        'is_complete': progress.is_complete,
        'organization_count': progress.organization_count,
        'venue_count': progress.venue_count,
        'piano_count': progress.piano_count,
        'active_member_count': progress.active_member_count,
        'pending_invitation_count': progress.pending_invitation_count,
    }


def _user_can_view_company_media(user, company):
    return user.is_authenticated and user.membership_for_company(company) is not None


def _activity_events(company, target, *, limit=5):
    return target_audit_events(company=company, target=target, limit=limit)


def _send_company_invitation_email(request, invitation):
    invite_url = request.build_absolute_uri(
        reverse('company_invitation_accept', args=[invitation.token])
    )
    send_mail(
        subject=f"Invitation to join {invitation.company.name}",
        message=(
            f"You've been invited to join {invitation.company.name} in Overtone.\n\n"
            f"Accept your invitation here:\n{invite_url}\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
        fail_silently=False,
    )


# ── Role-based access ────────────────────────────────────────────

def admin_required(view_func):
    """Decorator: requires login + admin role."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not _user_is_company_admin(request):
            messages.error(request, 'Admin access required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def staff_required(view_func):
    """Decorator: requires login + an app role."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (_user_is_company_admin(request) or _user_is_company_technician(request)):
            messages.error(request, 'Technician access required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
def toggle_tech_mode(request):
    membership = getattr(request, 'active_membership', None)
    if not (membership and membership.is_active and membership.role_admin and membership.role_technician):
        messages.error(request, 'Tech Mode is only available to admin technicians.')
        return redirect('dashboard')

    if request.method == 'POST':
        enabled = request.POST.get('tech_mode') == 'on'
        request.session['tech_mode'] = enabled
        messages.success(request, 'Tech Mode enabled.' if enabled else 'Admin Mode enabled.')

    return_url = _safe_return_url(request, reverse('dashboard'))
    return HttpResponseRedirect(return_url)


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
                company=piano.company,
                piano=piano,
                reported_by_name=name,
                reported_by_email=email,
                issue_description=issue,
                status='Assigned',
            )
            wo = WorkOrder.objects.create(
                company=piano.company,
                piano=piano,
                order_type=WorkOrder.OrderType.REQUEST,
                status=WorkOrder.Status.OPEN,
                priority=WorkOrder.Priority.NORMAL,
                description=issue,
            )
            mr.work_order = wo
            mr.save()
            notify_maintenance_request(mr, wo, request)
            return render(request, 'maintenance/maintenance_request_success.html', {
                'piano': piano,
                'maintenance_request': mr,
                'work_order': wo,
            })

    return render(request, 'maintenance/maintenance_request_form.html',
                  {'piano': piano})


# ── Dashboard ──────────────────────────────────────────────────────

@login_required
def dashboard(request):
    today = date.today()
    month_start = today.replace(day=1)
    user = request.user
    company = ensure_company_access(request)
    tech_mode = _is_tech_mode(request)
    is_admin = _user_is_company_admin(request) and not tech_mode
    setup_progress = _setup_progress_context(company) if is_admin else None

    if is_admin:
        # Admin sees everything
        wo_base = WorkOrder.objects.filter(company=company)
        overdue_count = wo_base.filter(
            status__in=[WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS],
            due_date__lt=today,
        ).count()
        open_wo_count = wo_base.filter(status=WorkOrder.Status.OPEN).count()
        in_progress_count = wo_base.filter(status=WorkOrder.Status.IN_PROGRESS).count()
        pending_request_count = MaintenanceRequest.objects.filter(
            company=company,
            status=MaintenanceRequest.RequestStatus.NEW,
        ).count()
        piano_count = Piano.objects.filter(company=company, is_active=True).count()
        venue_count = Venue.objects.filter(company=company).count()
        org_count = Organization.objects.filter(company=company).count()
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
        my_wos = WorkOrder.objects.filter(company=company, assigned_tech=user)
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
        'tech_mode': tech_mode,
        'overdue_count': overdue_count,
        'open_wo_count': open_wo_count,
        'in_progress_count': in_progress_count,
        'pending_request_count': pending_request_count,
        'piano_count': piano_count,
        'venue_count': venue_count,
        'org_count': org_count,
        'completed_this_month': completed_this_month,
        'dashboard_work_orders': dashboard_work_orders,
        'setup_progress': setup_progress,
    })


# ── Pianos ─────────────────────────────────────────────────────────

@login_required
def piano_list(request):
    today = date.today()
    soon = today + timedelta(days=30)
    company = ensure_company_access(request)

    qs, filters = _filtered_piano_queryset(request)

    return render(request, 'maintenance/piano_list.html', {
        'active_nav': 'pianos',
        'pianos': qs,
        'organizations': Organization.objects.filter(company=company),
        'venues': Venue.objects.filter(company=company),
        'tags': Tag.objects.filter(company=company),
        **filters,
        'today': today,
        'soon': soon,
    })


@admin_required
def piano_bulk_edit(request):
    company = ensure_company_access(request)
    qs, filters = _filtered_piano_queryset(request)
    pianos = list(qs)

    if request.method == 'POST':
        form = BulkPianoIntervalForm(request.POST, pianos=pianos)
        if form.is_valid():
            selected_ids = form.cleaned_data['piano_ids']
            updates = form.interval_updates()
            updated_count = qs.filter(pk__in=selected_ids).update(**updates)
            messages.success(
                request,
                f'Updated maintenance intervals for {updated_count} piano'
                f'{"s" if updated_count != 1 else ""}.',
            )
            return redirect(f'{request.path}?{request.GET.urlencode()}')
    else:
        initial = {'piano_ids': [piano.pk for piano in pianos]}
        form = BulkPianoIntervalForm(pianos=pianos, initial=initial)

    return render(request, 'maintenance/piano_bulk_edit.html', {
        'active_nav': 'pianos',
        'form': form,
        'pianos': pianos,
        'organizations': Organization.objects.filter(company=company),
        'venues': Venue.objects.filter(company=company),
        'tags': Tag.objects.filter(company=company),
        'type_choices': Piano.PianoType.choices,
        **filters,
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
        'open_work_orders': piano.work_orders.select_related('assigned_tech').exclude(
            status__in=[WorkOrder.Status.COMPLETE, WorkOrder.Status.CANCELLED],
        ).order_by('-created_at')[:20],
        'work_history': piano.work_orders.select_related('assigned_tech').filter(
            status=WorkOrder.Status.COMPLETE,
        ).order_by('-completed_date', '-created_at')[:20],
        'condition_readings': piano.condition_readings.order_by('-recorded_at')[:20],
        'custom_schedules': piano.schedules.all(),
        'today': today,
    }


@login_required
def piano_detail(request, pk):
    piano = get_object_or_404(
        Piano.objects.filter(company=ensure_company_access(request)).select_related('venue').prefetch_related('tags'),
        pk=pk,
    )
    ctx = _piano_context(piano)
    ctx['qr_url'] = request.build_absolute_uri(f'/maintenance_request/{piano.qr_code_token}/')
    ctx['photos'] = piano.photos.all()
    ctx['piano_tags'] = piano.tags.all()
    ctx['available_tags'] = Tag.objects.filter(company=piano.company, pianos__is_active=True).exclude(pk__in=piano.tags.all()).distinct()
    ctx['return_url'] = _safe_return_url(request, '/pianos/')
    ctx['workorder_return_url'] = _piano_detail_url(piano)
    ctx['activity_events'] = _activity_events(piano.company, piano)
    return render(request, 'maintenance/piano_detail.html', ctx)


@login_required
def photo_file(request, photo_pk):
    photo = get_object_or_404(Photo, pk=photo_pk)
    if not _user_can_view_company_media(request.user, photo.company):
        return HttpResponseForbidden("You do not have access to this photo.")

    storage = photo.image.storage
    if isinstance(storage, FileSystemStorage):
        content_type, _ = mimetypes.guess_type(photo.image.name)
        return FileResponse(photo.image.open("rb"), content_type=content_type or "application/octet-stream")

    return redirect(storage.url(photo.image.name, expire=settings.PRIVATE_MEDIA_URL_TTL))


@login_required
def piano_tab(request, pk, tab):
    piano = get_object_or_404(
        Piano.objects.filter(company=ensure_company_access(request)).select_related('venue'),
        pk=pk,
    )
    ctx = _piano_context(piano)
    ctx['workorder_return_url'] = _piano_detail_url(piano)
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
    company = ensure_company_access(request)
    if request.method == 'POST':
        form = PianoForm(request.POST, company=company)
        if form.is_valid():
            piano = form.save(commit=False)
            piano.company = company
            piano.save()
            form.save_m2m()
            log_audit_event(
                company=company,
                actor=request.user,
                event_type='piano.created',
                target=piano,
                message=f'Created piano {piano.name}.',
            )
            messages.success(request, f'Piano "{piano.name}" created.')
            return redirect('piano_detail', pk=piano.pk)
    else:
        form = PianoForm(company=company)

    return render(request, 'maintenance/piano_form.html', {
        'active_nav': 'pianos',
        'form': form,
        'piano': None,
        'venues': Venue.objects.filter(company=company),
        'type_choices': Piano.PianoType.choices,
    })


@admin_required
def piano_edit(request, pk):
    company = ensure_company_access(request)
    piano = get_object_or_404(Piano, company=company, pk=pk)

    if request.method == 'POST':
        form = PianoForm(request.POST, instance=piano, company=company)
        if form.is_valid():
            form.save()
            log_audit_event(
                company=company,
                actor=request.user,
                event_type='piano.updated',
                target=piano,
                message=f'Updated piano {piano.name}.',
            )
            messages.success(request, f'Piano "{piano.name}" updated.')
            return redirect('piano_detail', pk=piano.pk)
    else:
        form = PianoForm(instance=piano, company=company)

    return render(request, 'maintenance/piano_form.html', {
        'active_nav': 'pianos',
        'form': form,
        'piano': piano,
        'venues': Venue.objects.filter(company=company),
        'type_choices': Piano.PianoType.choices,
    })


@admin_required
def piano_deactivate(request, pk):
    piano = get_object_or_404(Piano, company=ensure_company_access(request), pk=pk)
    if request.method == 'POST':
        piano.is_active = False
        piano.save(update_fields=['is_active'])
        log_audit_event(
            company=piano.company,
            actor=request.user,
            event_type='piano.deactivated',
            target=piano,
            message=f'Deactivated piano {piano.name}.',
        )
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
        'available_tags': Tag.objects.filter(company=piano.company, pianos__is_active=True).exclude(pk__in=piano.tags.all()).distinct(),
    }


@admin_required
def piano_add_tag(request, pk):
    piano = get_object_or_404(Piano, company=ensure_company_access(request), pk=pk)
    if request.method == 'POST':
        tag_name = request.POST.get('tag_name', '').strip()
        if tag_name:
            tag, _ = Tag.objects.get_or_create(company=piano.company, name=tag_name)
            piano.tags.add(tag)
    if request.headers.get('HX-Request'):
        return render(request, 'maintenance/partials/piano_tags.html', _piano_tags_context(piano))
    return redirect('piano_detail', pk=piano.pk)


@admin_required
def piano_remove_tag(request, pk, tag_pk):
    piano = get_object_or_404(Piano, company=ensure_company_access(request), pk=pk)
    if request.method == 'POST':
        piano.tags.remove(tag_pk)
        if not Tag.objects.filter(company=piano.company, pk=tag_pk, pianos__is_active=True).exists():
            Tag.objects.filter(company=piano.company, pk=tag_pk).delete()
    if request.headers.get('HX-Request'):
        return render(request, 'maintenance/partials/piano_tags.html', _piano_tags_context(piano))
    return redirect('piano_detail', pk=piano.pk)


# ── Organizations ─────────────────────────────────────────────────

@login_required
def organization_list(request):
    organizations = _company_organizations(request).annotate(venue_count=Count('venues'))
    return render(request, 'maintenance/organization_list.html', {
        'active_nav': 'organizations',
        'organizations': organizations,
    })


@login_required
def organization_detail(request, pk):
    company = ensure_company_access(request)
    organization = get_object_or_404(Organization, company=company, pk=pk)
    venues = Venue.objects.filter(company=company, organization=organization).annotate(piano_count=Count('pianos'))
    return render(request, 'maintenance/organization_detail.html', {
        'active_nav': 'organizations',
        'organization': organization,
        'venues': venues,
        'activity_events': _activity_events(company, organization),
    })


@admin_required
def organization_create(request):
    company = ensure_company_access(request)
    if request.method == 'POST':
        form = OrganizationForm(request.POST, company=company)
        if form.is_valid():
            org = form.save(commit=False)
            org.company = company
            org.save()
            log_audit_event(company=company, actor=request.user, event_type='organization.created', target=org)
            messages.success(request, f'Organization "{org.name}" created.')
            return redirect('organization_detail', pk=org.pk)
    else:
        form = OrganizationForm(company=company)

    return render(request, 'maintenance/organization_form.html', {
        'active_nav': 'organizations',
        'form': form,
        'organization': None,
    })


@admin_required
def organization_edit(request, pk):
    company = ensure_company_access(request)
    organization = get_object_or_404(Organization, company=company, pk=pk)

    if request.method == 'POST':
        form = OrganizationForm(request.POST, instance=organization, company=company)
        if form.is_valid():
            form.save()
            log_audit_event(company=company, actor=request.user, event_type='organization.updated', target=organization)
            messages.success(request, f'Organization "{organization.name}" updated.')
            return redirect('organization_detail', pk=organization.pk)
    else:
        form = OrganizationForm(instance=organization, company=company)

    return render(request, 'maintenance/organization_form.html', {
        'active_nav': 'organizations',
        'form': form,
        'organization': organization,
    })


@admin_required
def organization_delete(request, pk):
    organization = get_object_or_404(Organization, company=ensure_company_access(request), pk=pk)
    venue_count = organization.venues.count()

    if request.method == 'POST':
        name = organization.name
        company = organization.company
        log_audit_event(
            company=company,
            actor=request.user,
            event_type='organization.deleted',
            target=organization,
            message=f'Deleted organization {name}.',
        )
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
    venues = _company_venues(request).select_related('organization').annotate(piano_count=Count('pianos'))
    return render(request, 'maintenance/venue_list.html', {
        'active_nav': 'venues',
        'venues': venues,
    })


@login_required
def venue_detail(request, pk):
    company = ensure_company_access(request)
    venue = get_object_or_404(Venue.objects.filter(company=company).select_related('organization'), pk=pk)
    pianos = Piano.objects.filter(company=company, venue=venue, is_active=True).select_related('venue')
    open_wo_count = WorkOrder.objects.filter(
        company=company,
        piano__venue=venue,
        status__in=[WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS],
    ).count()
    return render(request, 'maintenance/venue_detail.html', {
        'active_nav': 'venues',
        'venue': venue,
        'pianos': pianos,
        'open_wo_count': open_wo_count,
        'activity_events': _activity_events(company, venue),
    })


@admin_required
def venue_create(request):
    company = ensure_company_access(request)
    if request.method == 'POST':
        form = VenueForm(request.POST, company=company)
        if form.is_valid():
            venue = form.save(commit=False)
            venue.company = company
            venue.save()
            log_audit_event(company=company, actor=request.user, event_type='venue.created', target=venue)
            messages.success(request, f'Venue "{venue.name}" created.')
            return redirect('venue_detail', pk=venue.pk)
    else:
        form = VenueForm(company=company)

    return render(request, 'maintenance/venue_form.html', {
        'active_nav': 'venues',
        'form': form,
        'venue': None,
        'organizations': Organization.objects.filter(company=company),
    })


@admin_required
def venue_edit(request, pk):
    company = ensure_company_access(request)
    venue = get_object_or_404(Venue, company=company, pk=pk)

    if request.method == 'POST':
        form = VenueForm(request.POST, instance=venue, company=company)
        if form.is_valid():
            form.save()
            log_audit_event(company=company, actor=request.user, event_type='venue.updated', target=venue)
            messages.success(request, f'Venue "{venue.name}" updated.')
            return redirect('venue_detail', pk=venue.pk)
    else:
        form = VenueForm(instance=venue, company=company)

    return render(request, 'maintenance/venue_form.html', {
        'active_nav': 'venues',
        'form': form,
        'venue': venue,
        'organizations': Organization.objects.filter(company=company),
    })


@admin_required
def venue_delete(request, pk):
    company = ensure_company_access(request)
    venue = get_object_or_404(Venue.objects.filter(company=company).select_related('organization'), pk=pk)
    piano_count = Piano.objects.filter(company=company, venue=venue).count()

    if request.method == 'POST':
        name = venue.name
        org_pk = venue.organization_id
        log_audit_event(
            company=company,
            actor=request.user,
            event_type='venue.deleted',
            target=venue,
            message=f'Deleted venue {name}.',
        )
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
    today = date.today()
    company = ensure_company_access(request)
    qs, filters = _filtered_workorders(request)
    tech_mode = _is_tech_mode(request)

    sort_columns = []
    for key, label in [
        ('id', 'ID'),
        ('piano', 'Piano'),
        ('type', 'Order Type'),
        ('status', 'Status'),
        ('priority', 'Priority'),
        ('assigned', 'Assigned To'),
        ('due', 'Due'),
        ('completed', 'Completed'),
        ('created', 'Created'),
    ]:
        params = request.GET.copy()
        params['sort'] = key
        params['dir'] = 'desc' if filters['sort_key'] == key and filters['sort_dir'] == 'asc' else 'asc'
        sort_columns.append({
            'key': key,
            'label': label,
            'url': f'?{params.urlencode()}',
            'active': filters['sort_key'] == key,
        })

    context = {
        'active_nav': 'workorders',
        'work_orders': qs,
        'tech_mode': tech_mode,
        'sort_key': filters['sort_key'],
        'sort_dir': filters['sort_dir'],
        'sort_columns': sort_columns,
        'search_query': filters['search_query'],
        'status_filter': filters['status_filter'],
        'priority_filter': filters['priority_filter'],
        'type_filter': filters['type_filter'],
        'org_filter': filters['org_filter'],
        'venue_filter': filters['venue_filter'],
        'completed_from': filters['completed_from'],
        'completed_to': filters['completed_to'],
        'organizations': Organization.objects.filter(company=company),
        'venues': Venue.objects.filter(company=company),
        'technicians': company_users(company, technicians_only=True).order_by('first_name', 'last_name'),
        'status_choices': WorkOrder.Status.choices,
        'priority_choices': WorkOrder.Priority.choices,
        'type_choices': TaskType.choices,
        'today': today,
        'export_query': request.GET.urlencode(),
    }

    if request.headers.get('HX-Request') == 'true':
        return render(request, 'maintenance/partials/workorder_table.html', context)
    return render(request, 'maintenance/workorder_list.html', context)


@login_required
def workorder_detail(request, pk):
    company = ensure_company_access(request)
    wo = get_object_or_404(
        WorkOrder.objects.filter(company=company).select_related('piano', 'piano__venue', 'assigned_tech', 'schedule'),
        pk=pk,
    )
    user = request.user
    logs = wo.logs.select_related('technician').order_by('-logged_at')
    technicians = company_users(company, technicians_only=True).order_by('first_name', 'last_name')

    is_assigned_to_me = wo.assigned_tech_id == user.pk
    tech_mode = _is_tech_mode(request)
    can_edit_wo = _can_update_workorder(user, wo, tech_mode)
    return_url = _safe_return_url(request, '/work-orders/')

    today = date.today()

    return render(request, 'maintenance/workorder_detail.html', {
        'active_nav': 'workorders',
        'wo': wo,
        'logs': logs,
        'technicians': technicians,
        'today': today,
        'service_status': _service_status_context(wo, today),
        'can_edit_wo': can_edit_wo,
        'tech_mode': tech_mode,
        'is_assigned_to_me': is_assigned_to_me,
        'return_url': return_url,
        'activity_events': _activity_events(company, wo, limit=8),
    })


@admin_required
def workorder_create(request):
    company = ensure_company_access(request)
    if request.method == 'POST':
        form = WorkOrderForm(request.POST, company=company)
        if form.is_valid():
            wo = form.save(commit=False)
            wo.company = company
            wo.save()
            form.save_m2m()
            log_audit_event(company=company, actor=request.user, event_type='workorder.created', target=wo)
            if wo.assigned_tech_id:
                notify_work_order_assigned(wo, request)
            messages.success(request, f'Work Order WO-{wo.pk} created.')
            return redirect('workorder_detail', pk=wo.pk)
    else:
        initial = {}
        piano_pk = request.GET.get('piano')
        if piano_pk:
            initial['piano'] = piano_pk
        form = WorkOrderForm(initial=initial, company=company)

    return render(request, 'maintenance/workorder_form.html', {
        'active_nav': 'workorders',
        'form': form,
        'wo': None,
        'return_url': '/work-orders/',
        'form_title': 'Create Work Order',
        'submit_label': 'Create Work Order',
        'pianos': Piano.objects.filter(company=company, is_active=True).select_related('venue'),
        'venues': Venue.objects.filter(company=company),
        'technicians': company_users(company, technicians_only=True),
        'type_choices': WorkOrder.OrderType.choices,
        'task_type_choices': TaskType.choices,
        'status_choices': WorkOrder.Status.choices,
        'priority_choices': WorkOrder.Priority.choices,
    })


@login_required
def workorder_edit(request, pk):
    company = ensure_company_access(request)
    wo = get_object_or_404(
        WorkOrder.objects.filter(company=company).select_related('piano', 'assigned_tech'),
        pk=pk,
    )
    if not _can_update_workorder(request.user, wo, _is_tech_mode(request)):
        messages.error(request, 'You can only edit work orders assigned to you.')
        return HttpResponseRedirect(_workorder_detail_url(wo, _safe_return_url(request, '/work-orders/')))

    return_url = _safe_return_url(request, _workorder_detail_url(wo))
    if request.method == 'POST':
        previous_assigned_tech_id = wo.assigned_tech_id
        form = WorkOrderForm(request.POST, instance=wo, company=company)
        if form.is_valid():
            wo = form.save()
            log_audit_event(company=company, actor=request.user, event_type='workorder.updated', target=wo)
            if wo.assigned_tech_id and wo.assigned_tech_id != previous_assigned_tech_id:
                notify_work_order_assigned(wo, request)
            messages.success(request, f'Work Order WO-{wo.pk} updated.')
            return HttpResponseRedirect(_workorder_detail_url(wo, return_url))
    else:
        form = WorkOrderForm(instance=wo, company=company)

    return render(request, 'maintenance/workorder_form.html', {
        'active_nav': 'workorders',
        'form': form,
        'wo': wo,
        'return_url': return_url,
        'form_title': f'Edit WO-{wo.pk}',
        'submit_label': 'Save Changes',
        'pianos': Piano.objects.filter(company=company, is_active=True).select_related('venue'),
        'venues': Venue.objects.filter(company=company),
        'technicians': company_users(company, technicians_only=True),
        'type_choices': WorkOrder.OrderType.choices,
        'task_type_choices': TaskType.choices,
        'status_choices': WorkOrder.Status.choices,
        'priority_choices': WorkOrder.Priority.choices,
    })


@login_required
def workorder_assign(request, pk):
    company = ensure_company_access(request)
    wo = get_object_or_404(WorkOrder.objects.select_related('assigned_tech', 'piano'), company=company, pk=pk)
    user = request.user
    tech_mode = _is_tech_mode(request)
    previous_assigned_tech_id = wo.assigned_tech_id

    if request.method == 'POST':
        previous_status = wo.status
        if _user_is_company_admin(request) and not tech_mode:
            # Admin can assign any technician
            tech_id = request.POST.get('assigned_tech')
            if tech_id:
                try:
                    wo.assigned_tech = company_users(company, technicians_only=True).get(pk=int(tech_id))
                except (ValueError, TypeError):
                    pass
            else:
                wo.assigned_tech = None
        elif _user_is_company_technician(request):
            # Tech can only assign self to unassigned WOs
            action = request.POST.get('assign_action')
            if action == 'assign_self' and wo.assigned_tech is None:
                wo.assigned_tech = user

        if wo.status == WorkOrder.Status.OPEN and wo.assigned_tech_id:
            wo.status = WorkOrder.Status.IN_PROGRESS
        wo.save()

        if wo.assigned_tech_id != previous_assigned_tech_id or wo.status != previous_status:
            assignee_name = wo.assigned_tech.get_full_name() if wo.assigned_tech else 'Unassigned'
            log_audit_event(
                company=company,
                actor=request.user,
                event_type='workorder.assigned',
                target=wo,
                message=f'Assignment changed to {assignee_name}.',
                metadata={
                    'previous_assigned_tech_id': previous_assigned_tech_id,
                    'new_assigned_tech_id': wo.assigned_tech_id,
                    'previous_status': previous_status,
                    'new_status': wo.status,
                },
            )
        if wo.assigned_tech_id and wo.assigned_tech_id != previous_assigned_tech_id:
            notify_work_order_assigned(wo, request)

    technicians = company_users(company, technicians_only=True).order_by('first_name', 'last_name')
    return render(request, 'maintenance/partials/workorder_assign_cell.html', {
        'wo': wo,
        'technicians': technicians,
        'tech_mode': tech_mode,
    })


@login_required
def workorder_complete(request, pk):
    company = ensure_company_access(request)
    wo = get_object_or_404(
        WorkOrder.objects.filter(company=company).select_related('piano', 'assigned_tech'),
        pk=pk,
    )
    user = request.user
    return_url = _safe_return_url(request, f'/work-orders/{wo.pk}/')
    if wo.assigned_tech_id and (not _user_is_company_admin(request) or _is_tech_mode(request)) and wo.assigned_tech_id != user.pk:
        messages.error(request, 'You can only complete work orders assigned to you.')
        return HttpResponseRedirect(_workorder_detail_url(wo, return_url))

    parts = Part.objects.filter(company=company).order_by('name')

    if request.method == 'POST':
        form = WorkOrderCompleteForm(request.POST)
        if form.is_valid():
            today_date = date.today()
            if wo.assigned_tech_id is None:
                wo.assigned_tech = user

            # Create the maintenance log
            tech = wo.assigned_tech or request.user
            log = MaintenanceLog.objects.create(
                company=company,
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
                    Photo.objects.create(company=company, piano=wo.piano, work_order=wo, image=f, caption='')

            # Handle parts used
            part_ids = request.POST.getlist('part_id')
            part_qtys = request.POST.getlist('part_qty')
            for pid, qty in zip(part_ids, part_qtys):
                if pid and qty:
                    try:
                        part = Part.objects.get(company=company, pk=int(pid))
                        qty_int = int(qty)
                        if qty_int > 0:
                            PartUsed.objects.create(
                                company=company,
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
                    company=company,
                    piano=wo.piano,
                    log=log,
                    **cr_data,
                )
                reading.update_piano_current_state()

            log_audit_event(company=company, actor=request.user, event_type='workorder.completed', target=wo)
            messages.success(request, f'Work Order WO-{wo.pk} completed.')
            return HttpResponseRedirect(_workorder_detail_url(wo, return_url))
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
        'return_url': return_url,
    })


@admin_required
def workorder_delete(request, pk):
    company = ensure_company_access(request)
    wo = get_object_or_404(
        WorkOrder.objects.filter(company=company).select_related('piano', 'piano__venue'),
        pk=pk,
    )
    return_url = _safe_return_url(request, reverse('workorder_list'))
    log_count = wo.logs.count()

    if request.method == 'POST':
        wo_id = wo.pk
        log_audit_event(
            company=company,
            actor=request.user,
            event_type='workorder.deleted',
            target=wo,
            message=f'Deleted work order WO-{wo_id}.',
        )
        wo.delete()
        messages.success(request, f'Work Order WO-{wo_id} deleted.')
        return HttpResponseRedirect(return_url)

    return render(request, 'maintenance/workorder_confirm_delete.html', {
        'active_nav': 'workorders',
        'wo': wo,
        'log_count': log_count,
        'return_url': return_url,
    })


@login_required
def workorder_reopen(request, pk):
    wo = get_object_or_404(WorkOrder, company=ensure_company_access(request), pk=pk)
    return_url = _safe_return_url(request, _workorder_detail_url(wo))

    if request.method != 'POST':
        return HttpResponseRedirect(_workorder_detail_url(wo, return_url))
    if not _can_update_workorder(request.user, wo, _is_tech_mode(request)):
        messages.error(request, 'You can only reopen work orders assigned to you.')
        return HttpResponseRedirect(_workorder_detail_url(wo, return_url))
    if wo.status != WorkOrder.Status.COMPLETE:
        messages.info(request, f'WO-{wo.pk} is already open.')
        return HttpResponseRedirect(_workorder_detail_url(wo, return_url))

    wo.status = WorkOrder.Status.IN_PROGRESS if wo.assigned_tech_id else WorkOrder.Status.OPEN
    wo.completed_date = None
    wo.save(update_fields=['status', 'completed_date'])
    log_audit_event(company=wo.company, actor=request.user, event_type='workorder.reopened', target=wo)
    messages.success(request, f'WO-{wo.pk} reopened.')
    return HttpResponseRedirect(_workorder_detail_url(wo, return_url))


@login_required
def workorder_log_work(request, pk):
    """Log work against a work order without completing it."""
    company = ensure_company_access(request)
    wo = get_object_or_404(
        WorkOrder.objects.filter(company=company).select_related('piano', 'piano__venue', 'assigned_tech'),
        pk=pk,
    )
    user = request.user
    return_url = _safe_return_url(request, f'/work-orders/{wo.pk}/')
    if wo.assigned_tech_id and (not _user_is_company_admin(request) or _is_tech_mode(request)) and wo.assigned_tech_id != user.pk:
        messages.error(request, 'You can only log work on work orders assigned to you.')
        return HttpResponseRedirect(_workorder_detail_url(wo, return_url))

    parts = Part.objects.filter(company=company).order_by('name')

    if request.method == 'POST':
        form = WorkOrderLogWorkForm(request.POST)
        if form.is_valid():
            if wo.assigned_tech_id is None:
                wo.assigned_tech = user

            tech = wo.assigned_tech or request.user
            log = MaintenanceLog.objects.create(
                company=company,
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
                    Photo.objects.create(company=company, piano=wo.piano, work_order=wo, image=f, caption='')

            # Handle parts used
            part_ids = request.POST.getlist('part_id')
            part_qtys = request.POST.getlist('part_qty')
            for pid, qty in zip(part_ids, part_qtys):
                if pid and qty:
                    try:
                        part = Part.objects.get(company=company, pk=int(pid))
                        qty_int = int(qty)
                        if qty_int > 0:
                            PartUsed.objects.create(
                                company=company,
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
                wo.save(update_fields=['assigned_tech', 'status'])
            elif wo.assigned_tech_id == user.pk:
                wo.save(update_fields=['assigned_tech'])

            log_audit_event(company=company, actor=request.user, event_type='workorder.work_logged', target=wo)
            messages.success(request, f'Work logged for WO-{wo.pk}.')
            return HttpResponseRedirect(_workorder_detail_url(wo, return_url))
    else:
        form = WorkOrderLogWorkForm()

    return render(request, 'maintenance/workorder_log_work.html', {
        'active_nav': 'workorders',
        'wo': wo,
        'form': form,
        'parts': parts,
        'return_url': return_url,
    })


@login_required
def workorder_export_csv(request):
    qs, _ = _filtered_workorders(request)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="work_orders.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Piano', 'Venue', 'Order Type', 'Status', 'Priority',
        'Assigned To', 'Due Date', 'Completed', 'Created', 'Description',
    ])
    for wo in qs:
        writer.writerow([
            f'WO-{wo.pk}',
            wo.piano.name if wo.piano else wo.piano_name,
            wo.piano.venue.name if wo.piano and wo.piano.venue else '',
            wo.task_type or wo.order_type,
            wo.status,
            wo.priority,
            wo.assigned_tech.get_full_name() if wo.assigned_tech else '',
            wo.due_date or '',
            wo.completed_date or '',
            wo.created_at.strftime('%Y-%m-%d'),
            wo.description,
        ])
    return response


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
    piano = get_object_or_404(Piano, company=ensure_company_access(request), pk=pk)
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
            Photo.objects.create(company=piano.company, piano=piano, image=f, caption=caption, is_profile_photo=is_profile)
            uploaded += 1
        if uploaded:
            log_audit_event(
                company=piano.company,
                actor=request.user,
                event_type='piano.photo_uploaded',
                target=piano,
                message=f'Uploaded {uploaded} photo(s).',
                metadata={'uploaded_count': uploaded},
            )
            messages.success(request, f'{uploaded} photo(s) uploaded.')
        return redirect('piano_detail', pk=piano.pk)

    return render(request, 'maintenance/piano_photo_upload.html', {
        'active_nav': 'pianos',
        'piano': piano,
    })


@login_required
def piano_set_profile_photo(request, pk, photo_pk):
    piano = get_object_or_404(Piano, company=ensure_company_access(request), pk=pk)
    if request.method == 'POST':
        piano.photos.update(is_profile_photo=False)
        Photo.objects.filter(pk=photo_pk, piano=piano).update(is_profile_photo=True)
    return redirect('piano_detail', pk=piano.pk)


@staff_required
def piano_photo_delete(request, pk, photo_pk):
    piano = get_object_or_404(Piano, company=ensure_company_access(request), pk=pk)
    photo = get_object_or_404(Photo, company=piano.company, pk=photo_pk, piano=piano)

    if request.method == 'POST':
        was_profile = photo.is_profile_photo
        photo_name = photo.image.name if photo.image else ''
        if photo.image:
            photo.image.delete(save=False)
        photo.delete()

        if was_profile:
            next_photo = piano.photos.order_by('-uploaded_at').first()
            if next_photo:
                next_photo.is_profile_photo = True
                next_photo.save(update_fields=['is_profile_photo'])

        log_audit_event(
            company=piano.company,
            actor=request.user,
            event_type='piano.photo_deleted',
            target=piano,
            message='Deleted a piano photo.',
            metadata={'was_profile_photo': was_profile, 'image_name': photo_name},
        )
        messages.success(request, 'Photo deleted.')
    return redirect('piano_detail', pk=piano.pk)


# ── Slice 6: Schedule ────────────────────────────────────────────

@login_required
def schedule(request):
    today = date.today()
    soon = today + timedelta(days=30)
    due_filter = request.GET.get('due', '')
    org_filter = request.GET.get('org', '')
    venue_filter = request.GET.get('venue', '')
    company = ensure_company_access(request)

    active_statuses = [WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS]
    active_wos = (
        WorkOrder.objects
        .filter(company=company, status__in=active_statuses)
        .select_related('piano', 'piano__venue', 'assigned_tech')
    )
    if org_filter:
        active_wos = active_wos.filter(piano__venue__organization_id=org_filter)
    if venue_filter:
        active_wos = active_wos.filter(piano__venue_id=venue_filter)
    if due_filter == 'overdue':
        active_wos = active_wos.filter(due_date__lt=today)
    elif due_filter == 'next-30':
        active_wos = active_wos.filter(due_date__gte=today, due_date__lte=soon)
    elif due_filter == 'upcoming':
        active_wos = active_wos.filter(due_date__gt=soon)
    elif due_filter == 'no-date':
        active_wos = active_wos.filter(due_date__isnull=True)
    else:
        due_filter = ''

    schedule_columns = [
        {
            'label': 'Pianos Needing Tuning',
            'short_label': 'Tuning',
            'css_class': 'col-tuning',
            'work_orders': active_wos.filter(task_type=TaskType.TUNING).order_by('due_date', '-created_at'),
        },
        {
            'label': 'Pianos Needing Regulation',
            'short_label': 'Regulation',
            'css_class': 'col-regulation',
            'work_orders': active_wos.filter(task_type=TaskType.REGULATION).order_by('due_date', '-created_at'),
        },
        {
            'label': 'Pianos Needing Voicing',
            'short_label': 'Voicing',
            'css_class': 'col-voicing',
            'work_orders': active_wos.filter(task_type=TaskType.VOICING).order_by('due_date', '-created_at'),
        },
        {
            'label': 'Pianos Needing Cleaning',
            'short_label': 'Cleaning',
            'css_class': 'col-cleaning',
            'work_orders': active_wos.filter(task_type=TaskType.CLEANING).order_by('due_date', '-created_at'),
        },
    ]
    due_filter_choices = [
        ('', 'All'),
        ('overdue', 'Overdue'),
        ('next-30', 'Next 30 Days'),
        ('upcoming', 'Upcoming'),
        ('no-date', 'No Due Date'),
    ]
    schedule_query = {}
    if due_filter:
        schedule_query['due'] = due_filter
    if org_filter:
        schedule_query['org'] = org_filter
    if venue_filter:
        schedule_query['venue'] = venue_filter
    schedule_return_url = reverse('schedule')
    schedule_query_string = urlencode(schedule_query)
    if schedule_query_string:
        schedule_return_url = f'{schedule_return_url}?{schedule_query_string}'

    filter_base_query = {}
    if org_filter:
        filter_base_query['org'] = org_filter
    if venue_filter:
        filter_base_query['venue'] = venue_filter
    due_filter_links = []
    for value, label in due_filter_choices:
        link_query = filter_base_query.copy()
        if value:
            link_query['due'] = value
        query_string = urlencode(link_query)
        due_filter_links.append({
            'value': value,
            'label': label,
            'url': f'{reverse("schedule")}?{query_string}' if query_string else reverse('schedule'),
        })

    schedule_context = {
        'schedule_columns': schedule_columns,
        'due_filter': due_filter,
        'org_filter': org_filter,
        'venue_filter': venue_filter,
        'due_filter_choices': due_filter_choices,
        'due_filter_links': due_filter_links,
        'organizations': Organization.objects.filter(company=company),
        'venues': Venue.objects.filter(company=company),
        'schedule_return_url': schedule_return_url,
        'today': today,
    }
    if request.headers.get('HX-Request') == 'true':
        return render(request, 'maintenance/partials/schedule_board.html', schedule_context)

    return render(request, 'maintenance/schedule.html', {
        'active_nav': 'schedule',
        **schedule_context,
    })


# ── Slice 7: Requests ───────────────────────────────────────────

@login_required
def request_list(request):
    qs = (
        MaintenanceRequest.objects
        .filter(company=ensure_company_access(request))
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
    mr = get_object_or_404(MaintenanceRequest, company=ensure_company_access(request), pk=pk)
    if request.method == 'POST' and not mr.work_order:
        wo = WorkOrder.objects.create(
            company=mr.company,
            piano=mr.piano,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description=mr.issue_description,
        )
        mr.work_order = wo
        mr.status = MaintenanceRequest.RequestStatus.ASSIGNED
        mr.save()
        log_audit_event(
            company=mr.company,
            actor=request.user,
            event_type='maintenance_request.approved',
            target=mr,
            message=f'Approved request and created WO-{wo.pk}.',
        )
        messages.success(request, f'Request approved — WO-{wo.pk} created.')
    return redirect('request_list')


@admin_required
def request_reject(request, pk):
    mr = get_object_or_404(MaintenanceRequest, company=ensure_company_access(request), pk=pk)
    if request.method == 'POST':
        mr.status = MaintenanceRequest.RequestStatus.RESOLVED
        mr.save()
        log_audit_event(
            company=mr.company,
            actor=request.user,
            event_type='maintenance_request.rejected',
            target=mr,
            message='Marked request as resolved.',
        )
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
    piano = get_object_or_404(Piano, company=ensure_company_access(request), pk=piano_pk)

    if request.method == 'POST':
        form = ConditionReadingForm(request.POST)
        if form.is_valid():
            reading = form.save(commit=False)
            reading.company = piano.company
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
    templates = ScheduleTemplate.objects.filter(company=ensure_company_access(request))
    return render(request, 'maintenance/template_list.html', {
        'active_nav': 'schedule',
        'templates': templates,
    })


@admin_required
def template_create(request):
    company = ensure_company_access(request)
    if request.method == 'POST':
        form = ScheduleTemplateForm(request.POST)
        if form.is_valid():
            template = form.save(commit=False)
            template.company = company
            template.save()
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
    tmpl = get_object_or_404(ScheduleTemplate, company=ensure_company_access(request), pk=pk)
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
    company = ensure_company_access(request)
    tmpl = get_object_or_404(ScheduleTemplate, company=company, pk=pk)
    pianos = Piano.objects.filter(company=company, is_active=True).select_related('venue')

    if request.method == 'POST':
        piano_ids = request.POST.getlist('pianos')
        created = 0
        for pid in piano_ids:
            try:
                piano = Piano.objects.get(company=company, pk=int(pid))
            except (Piano.DoesNotExist, ValueError, TypeError):
                continue
            MaintenanceSchedule.objects.create(
                company=company,
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
    sched = get_object_or_404(MaintenanceSchedule, company=ensure_company_access(request), pk=pk)
    if request.method == 'POST':
        sched.is_active = not sched.is_active
        sched.save()
        state = 'resumed' if sched.is_active else 'paused'
        messages.success(request, f'Schedule "{sched.task_name}" {state}.')
    return redirect('piano_detail', pk=sched.piano_id)


@admin_required
def schedule_delete(request, pk):
    sched = get_object_or_404(MaintenanceSchedule, company=ensure_company_access(request), pk=pk)
    piano_pk = sched.piano_id
    if request.method == 'POST':
        sched.delete()
        messages.success(request, 'Schedule removed.')
    return redirect('piano_detail', pk=piano_pk)


# ── Slice 10: Technicians ───────────────────────────────────────

@admin_required
def technician_list(request):
    company = ensure_company_access(request)
    memberships = list(
        CompanyMembership.objects
        .filter(company=company)
        .select_related('user')
        .annotate(
            open_work_order_count=Count(
                'user__work_orders',
                filter=Q(
                    user__work_orders__status__in=[
                        WorkOrder.Status.OPEN,
                        WorkOrder.Status.IN_PROGRESS,
                    ],
                    user__work_orders__company=company,
                ),
            ),
        )
        .order_by('-is_active', '-user__is_active', 'user__first_name', 'user__last_name', 'user__username')
    )
    techs = []
    for membership in memberships:
        tech = membership.user
        tech.company_membership = membership
        tech.open_work_order_count = membership.open_work_order_count
        techs.append(tech)
    return render(request, 'maintenance/technician_list.html', {
        'active_nav': 'technicians',
        'technicians': techs,
    })


@admin_required
def technician_create(request):
    company = ensure_company_access(request)
    if request.method == 'POST':
        form = TechnicianCreateForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role_admin = False
            user.role_technician = False
            user.save()
            CompanyMembership.objects.update_or_create(
                company=company,
                user=user,
                defaults={
                    'role_admin': form.cleaned_data['role_admin'],
                    'role_technician': form.cleaned_data['role_technician'],
                    'is_active': user.is_active,
                },
            )
            log_audit_event(company=company, actor=request.user, event_type='membership.created', target=user)
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
    company = ensure_company_access(request)
    membership = get_object_or_404(
        CompanyMembership.objects.select_related('user'),
        company=company,
        user_id=pk,
    )
    tech = membership.user
    original_account_active = tech.is_active
    if request.method == 'POST':
        form = TechnicianUpdateForm(request.POST, instance=tech)
        if form.is_valid():
            updated = form.save(commit=False)
            desired_membership_active = form.cleaned_data['is_active']
            membership_was_active = membership.is_active
            updated.is_active = original_account_active
            if updated.pk == request.user.pk:
                if not desired_membership_active:
                    form.add_error('is_active', 'You cannot deactivate your own access to this company.')
                if not form.cleaned_data.get('role_admin'):
                    form.add_error('role_admin', 'You cannot remove your own admin role.')
            if not form.errors:
                updated.save()
                membership.role_admin = form.cleaned_data['role_admin']
                membership.role_technician = form.cleaned_data['role_technician']
                membership.is_active = desired_membership_active
                membership.save()
                event_type = 'membership.updated'
                message = 'Updated membership roles.'
                if membership_was_active != desired_membership_active:
                    event_type = 'membership.activated' if desired_membership_active else 'membership.deactivated'
                    message = (
                        'Activated company access.'
                        if desired_membership_active
                        else 'Deactivated company access.'
                    )
                log_audit_event(
                    company=company,
                    actor=request.user,
                    event_type=event_type,
                    target=tech,
                    message=message,
                )
                messages.success(request, f'User {updated.username} updated.')
                return redirect('technician_list')
    else:
        form = TechnicianUpdateForm(instance=tech)
        form.fields['is_active'].initial = membership.is_active
        form.fields['role_admin'].initial = membership.role_admin
        form.fields['role_technician'].initial = membership.role_technician
    return render(request, 'maintenance/technician_form.html', {
        'active_nav': 'technicians',
        'form': form,
        'editing': True,
        'technician': tech,
    })


@admin_required
def technician_toggle_membership(request, pk):
    company = ensure_company_access(request)
    membership = get_object_or_404(
        CompanyMembership.objects.select_related('user'),
        company=company,
        user_id=pk,
    )
    tech = membership.user

    if request.method != 'POST':
        return redirect('technician_list')

    if tech.pk == request.user.pk and membership.is_active:
        messages.error(request, 'You cannot deactivate your own access to this company.')
        return redirect('technician_list')

    membership.is_active = not membership.is_active
    membership.save()
    activated = membership.is_active
    log_audit_event(
        company=company,
        actor=request.user,
        event_type='membership.activated' if activated else 'membership.deactivated',
        target=tech,
        message='Activated company access.' if activated else 'Deactivated company access.',
    )
    if activated:
        messages.success(request, f'{tech.get_full_name() or tech.username} is active in {company.name} again.')
    else:
        messages.success(request, f'{tech.get_full_name() or tech.username} was removed from the active roster for {company.name}.')
    return redirect('technician_list')


@admin_required
def technician_report(request):
    company = ensure_company_access(request)
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    log_q = Q()
    if date_from:
        log_q &= Q(logs__logged_at__date__gte=date_from)
    if date_to:
        log_q &= Q(logs__logged_at__date__lte=date_to)

    techs = (
        company_users(company)
        .filter(is_active=True)
        .annotate(
            total_hours=Coalesce(
                Sum('logs__hours_worked', filter=log_q & Q(logs__company=company)),
                Decimal('0'),
                output_field=DecimalField(),
            ),
            wo_count=Count(
                'logs__work_order',
                distinct=True,
                filter=log_q & Q(logs__company=company),
            ),
            last_activity=Max(
                'logs__logged_at',
                filter=log_q & Q(logs__company=company),
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
    company = ensure_company_access(request)
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    log_q = Q()
    if date_from:
        log_q &= Q(logs__logged_at__date__gte=date_from)
    if date_to:
        log_q &= Q(logs__logged_at__date__lte=date_to)

    techs = (
        company_users(company)
        .filter(is_active=True)
        .annotate(
            total_hours=Coalesce(
                Sum('logs__hours_worked', filter=log_q & Q(logs__company=company)),
                Decimal('0'),
                output_field=DecimalField(),
            ),
            wo_count=Count(
                'logs__work_order',
                distinct=True,
                filter=log_q & Q(logs__company=company),
            ),
            last_activity=Max(
                'logs__logged_at',
                filter=log_q & Q(logs__company=company),
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
    parts = Part.objects.filter(company=ensure_company_access(request))
    return render(request, 'maintenance/part_list.html', {
        'active_nav': 'parts',
        'parts': parts,
    })


@admin_required
def part_create(request):
    company = ensure_company_access(request)
    if request.method == 'POST':
        form = PartForm(request.POST)
        if form.is_valid():
            part = form.save(commit=False)
            part.company = company
            part.save()
            log_audit_event(
                company=company,
                actor=request.user,
                event_type='part.created',
                target=part,
                message=f'Created part {part.name}.',
            )
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
    part = get_object_or_404(Part, company=ensure_company_access(request), pk=pk)
    if request.method == 'POST':
        form = PartForm(request.POST, instance=part)
        if form.is_valid():
            form.save()
            log_audit_event(
                company=part.company,
                actor=request.user,
                event_type='part.updated',
                target=part,
                message=f'Updated part {part.name}.',
            )
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
    company = ensure_company_access(request)
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
                org, _ = Organization.objects.get_or_create(company=company, name=org_name) if org_name else (None, False)
                if not org:
                    org = Organization.objects.filter(company=company).first()
                    if not org:
                        org = Organization.objects.create(company=company, name='Default Organization')
                venue, _ = Venue.objects.get_or_create(
                    company=company,
                    name=venue_name,
                    defaults={'organization': org},
                )
                Piano.objects.create(
                    company=company,
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
            log_audit_event(
                company=company,
                actor=request.user,
                event_type='piano.imported',
                message=f'Imported {created} piano(s) from CSV.',
                metadata={'created_count': created, 'error_count': len(errors)},
            )
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
    pianos = Piano.objects.filter(company=ensure_company_access(request), is_active=True).select_related('venue').order_by('venue__name', 'name')
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
    pianos = Piano.objects.filter(company=ensure_company_access(request), is_active=True).select_related('venue').order_by('venue__name', 'name')
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
    company = ensure_company_access(request)
    log_audit_event(
        company=company,
        actor=request.user,
        event_type='report.workorders_exported',
        message='Exported work orders CSV.',
    )
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="work_orders.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'Piano', 'Venue', 'Type', 'Status', 'Priority',
                     'Assigned To', 'Due Date', 'Completed', 'Created', 'Description'])
    wos = WorkOrder.objects.filter(company=company).select_related('piano', 'piano__venue', 'assigned_tech').order_by('-created_at')
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
    company = ensure_company_access(request)
    log_audit_event(
        company=company,
        actor=request.user,
        event_type='report.pianos_exported',
        message='Exported pianos CSV.',
    )
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="pianos.csv"'
    writer = csv.writer(response)
    writer.writerow(['Name', 'Make', 'Model', 'Serial Number', 'Type',
                     'Venue', 'Section', 'Room', 'Year Built', 'Year Acquired', 'Notes'])
    pianos = Piano.objects.filter(company=company, is_active=True).select_related('venue').order_by('name')
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
    is_admin = _user_is_company_admin(request)
    active_company = ensure_company_access(request)
    setup_progress = _setup_progress_context(active_company) if is_admin else None
    company_settings = CompanySettings.load_for_company(active_company) if is_admin else None
    company_form = CompanySettingsForm(instance=company_settings, prefix='company') if is_admin else None
    profile_form = UserProfileForm(instance=request.user, prefix='profile')
    password_form = PasswordChangeForm(user=request.user, prefix='password')
    invitation_form = CompanyInvitationForm(prefix='invite') if is_admin else None
    pending_invitations = (
        CompanyInvitation.objects.filter(
            company=active_company,
            status=CompanyInvitation.Status.PENDING,
        ).order_by('-created_at')
        if is_admin else []
    )
    recent_invitations = (
        CompanyInvitation.objects.filter(company=active_company)
        .exclude(status=CompanyInvitation.Status.PENDING)
        .order_by('-created_at')[:10]
        if is_admin else []
    )

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'company' and is_admin:
            company_form = CompanySettingsForm(
                request.POST, instance=company_settings, prefix='company',
            )
            if company_form.is_valid():
                company_form.save()
                log_audit_event(
                    company=active_company,
                    actor=request.user,
                    event_type='company_settings.updated',
                    target=company_settings,
                    message='Updated company settings.',
                )
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

        elif action == 'invite' and is_admin:
            invitation_form = CompanyInvitationForm(request.POST, prefix='invite')
            if invitation_form.is_valid():
                invitation = invitation_form.save(commit=False)
                invitation.company = active_company
                invitation.invited_by = request.user
                invitation.expires_at = timezone.now() + timedelta(days=7)
                invitation.save()
                _send_company_invitation_email(request, invitation)
                log_audit_event(company=active_company, actor=request.user, event_type='invitation.created', target=invitation)
                messages.success(request, f'Invitation sent to {invitation.email}.')
                return redirect('settings')

        elif action == 'invite_revoke' and is_admin:
            invitation = get_object_or_404(
                CompanyInvitation,
                company=active_company,
                pk=request.POST.get('invitation_id'),
                status=CompanyInvitation.Status.PENDING,
            )
            invitation.status = CompanyInvitation.Status.REVOKED
            invitation.save(update_fields=['status'])
            log_audit_event(company=active_company, actor=request.user, event_type='invitation.revoked', target=invitation)
            messages.success(request, f'Invitation revoked for {invitation.email}.')
            return redirect('settings')

        elif action == 'invite_resend' and is_admin:
            invitation = get_object_or_404(
                CompanyInvitation,
                company=active_company,
                pk=request.POST.get('invitation_id'),
                status=CompanyInvitation.Status.PENDING,
            )
            invitation.token = uuid.uuid4()
            invitation.expires_at = timezone.now() + timedelta(days=7)
            invitation.save(update_fields=['token', 'expires_at'])
            _send_company_invitation_email(request, invitation)
            log_audit_event(company=active_company, actor=request.user, event_type='invitation.resent', target=invitation)
            messages.success(request, f'Invitation resent to {invitation.email}.')
            return redirect('settings')

    return render(request, 'maintenance/settings.html', {
        'active_nav': 'settings',
        'company_form': company_form,
        'profile_form': profile_form,
        'password_form': password_form,
        'invitation_form': invitation_form,
        'pending_invitations': pending_invitations,
        'recent_invitations': recent_invitations,
        'setup_progress': setup_progress,
    })


@login_required
def switch_company(request):
    if request.method != 'POST':
        return redirect('dashboard')

    form = CompanySwitcherForm(request.POST)
    if form.is_valid():
        company_id = form.cleaned_data['company_id']
        if request.user.membership_for_company(company_id):
            request.session[ACTIVE_COMPANY_SESSION_KEY] = company_id
            messages.success(request, 'Active company updated.')
    return redirect(request.POST.get('next') or 'dashboard')


def company_invitation_accept(request, token):
    invitation = get_object_or_404(
        CompanyInvitation.objects.select_related('company'),
        token=token,
    )
    if invitation.status != CompanyInvitation.Status.PENDING or invitation.is_expired:
        messages.error(request, 'This invitation is no longer valid.')
        return redirect('login')

    if request.user.is_authenticated:
        user = request.user
        if invitation.email and user.email and invitation.email.lower() != user.email.lower():
            messages.error(request, 'Please sign in with the invited email address to accept this invitation.')
            return redirect('settings')
        CompanyMembership.objects.update_or_create(
            company=invitation.company,
            user=user,
            defaults={
                'role_admin': invitation.role_admin,
                'role_technician': invitation.role_technician,
                'is_active': True,
            },
        )
        invitation.status = CompanyInvitation.Status.ACCEPTED
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=['status', 'accepted_at'])
        request.session[ACTIVE_COMPANY_SESSION_KEY] = invitation.company_id
        messages.success(request, f'You joined {invitation.company.name}.')
        return redirect('dashboard')

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = True
            user.email = invitation.email
            user.role_admin = False
            user.role_technician = False
            user.save()
            CompanyMembership.objects.update_or_create(
                company=invitation.company,
                user=user,
                defaults={
                    'role_admin': invitation.role_admin,
                    'role_technician': invitation.role_technician,
                    'is_active': True,
                },
            )
            invitation.status = CompanyInvitation.Status.ACCEPTED
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=['status', 'accepted_at'])
            messages.success(request, 'Account created. You can sign in now.')
            return redirect('login')
    else:
        form = SignUpForm(initial={
            'email': invitation.email,
            'first_name': invitation.first_name,
            'last_name': invitation.last_name,
        })

    return render(request, 'registration/signup.html', {
        'form': form,
        'invitation': invitation,
    })
