from datetime import date, timedelta

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import Location, Piano, MaintenanceSchedule, ScheduleTemplate, WorkOrder, Technician
from .serializers import (
    LocationSerializer,
    PianoSerializer,
    MaintenanceScheduleSerializer,
    ScheduleTemplateSerializer,
    WorkOrderSerializer,
    TechnicianMinimalSerializer,
)


class LocationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Location.objects.all().order_by('name')
    serializer_class = LocationSerializer


class PianoViewSet(viewsets.ModelViewSet):
    queryset = Piano.objects.select_related('location').order_by('location__name', 'name')
    serializer_class = PianoSerializer


class ScheduleTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = ScheduleTemplateSerializer

    def get_queryset(self):
        return ScheduleTemplate.objects.prefetch_related('schedules').order_by('name')

    @action(detail=True, methods=['post'])
    def apply_to_pianos(self, request, pk=None):
        template = self.get_object()
        piano_ids = request.data.get('piano_ids', [])
        if not piano_ids:
            return Response({'error': 'No pianos selected.'}, status=status.HTTP_400_BAD_REQUEST)

        pianos = Piano.objects.filter(id__in=piano_ids)
        created = []
        for piano in pianos:
            schedule = MaintenanceSchedule.objects.create(
                piano=piano,
                template=template,
                task_name=template.task_name,
                task_type=template.task_type,
                interval_days=template.interval_days,
                warning_days_before=template.warning_days_before,
            )
            created.append(schedule.id)

        return Response({'created': len(created), 'schedule_ids': created})


class MaintenanceScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceScheduleSerializer

    def get_queryset(self):
        return MaintenanceSchedule.objects.select_related(
            'piano__location', 'template'
        ).order_by('piano__location__name', 'piano__name', 'task_type')


class WorkOrderViewSet(viewsets.ModelViewSet):
    serializer_class = WorkOrderSerializer

    def get_queryset(self):
        return WorkOrder.objects.select_related(
            'piano__location', 'assigned_tech', 'schedule'
        ).order_by('-created_at')


class TechnicianViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Technician.objects.filter(is_active=True).order_by('first_name', 'last_name')
    serializer_class = TechnicianMinimalSerializer


@api_view(['GET'])
def calendar_events(request):
    """
    Returns unified calendar events for a date range.
    Query params: start=YYYY-MM-DD, end=YYYY-MM-DD
    Each event: { id, type, title, date, status, priority, color,
                  piano_name, piano_id, work_order_id?, schedule_id? }
    """
    try:
        start = date.fromisoformat(request.query_params.get('start', str(date.today().replace(day=1))))
        end   = date.fromisoformat(request.query_params.get('end',   str(date.today())))
    except ValueError:
        return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

    events = []

    # ── Work Orders ───────────────────────────────────────────────────────────
    work_orders = WorkOrder.objects.select_related('piano__location', 'assigned_tech').filter(
        due_date__gte=start, due_date__lte=end
    )
    STATUS_COLOR = {
        'Open':        '#3b82f6',   # blue
        'In Progress': '#f59e0b',   # amber
        'Complete':    '#22c55e',   # green
        'Cancelled':   '#9ca3af',   # grey
    }
    PRIORITY_DOT = {
        'Urgent': '🔴',
        'High':   '🟠',
        'Normal': '🔵',
        'Low':    '⚪',
    }
    for wo in work_orders:
        events.append({
            'id':            f'wo_{wo.id}',
            'type':          'work_order',
            'title':         f'{wo.piano.name} — {wo.order_type}',
            'date':          str(wo.due_date),
            'status':        wo.status,
            'priority':      wo.priority,
            'color':         STATUS_COLOR.get(wo.status, '#3b82f6'),
            'priority_dot':  PRIORITY_DOT.get(wo.priority, '🔵'),
            'piano_name':    wo.piano.name,
            'piano_brand':   wo.piano.brand,
            'piano_location': wo.piano.location.name,
            'piano_id':      wo.piano_id,
            'work_order_id': wo.id,
            'description':   wo.description,
            'assigned_tech': wo.assigned_tech.get_full_name() if wo.assigned_tech else None,
        })

    # ── Upcoming Schedule Occurrences ─────────────────────────────────────────
    schedules = MaintenanceSchedule.objects.select_related('piano__location').filter(is_active=True)

    # Build a map of schedule_id → last completed work-order date
    last_completed = {}
    completed_wos = WorkOrder.objects.filter(
        schedule__isnull=False,
        status='Complete',
        completed_date__isnull=False,
    ).values('schedule_id', 'completed_date').order_by('schedule_id', '-completed_date')
    seen = set()
    for row in completed_wos:
        sid = row['schedule_id']
        if sid not in seen:
            last_completed[sid] = row['completed_date']
            seen.add(sid)

    TASK_COLOR = {
        'Tuning':     '#7c3aed',
        'Regulation': '#2563eb',
        'Voicing':    '#d97706',
        'Cleaning':   '#059669',
        'Inspection': '#db2777',
        'Other':      '#6b7280',
    }

    today = date.today()
    for sched in schedules:
        anchor = last_completed.get(sched.id, today - timedelta(days=sched.interval_days))
        # Walk forward from anchor to generate occurrences within [start, end]
        occ = anchor + timedelta(days=sched.interval_days)
        while occ <= end:
            if occ >= start:
                warn_date = occ - timedelta(days=sched.warning_days_before)
                is_overdue  = occ < today
                is_warning  = not is_overdue and warn_date <= today
                events.append({
                    'id':            f'sched_{sched.id}_{occ}',
                    'type':          'schedule',
                    'title':         f'{sched.piano.name} — {sched.task_name}',
                    'date':          str(occ),
                    'status':        'Overdue' if is_overdue else ('Due Soon' if is_warning else 'Upcoming'),
                    'priority':      None,
                    'color':         '#ef4444' if is_overdue else ('#f59e0b' if is_warning else TASK_COLOR.get(sched.task_type, '#6b7280')),
                    'task_type':     sched.task_type,
                    'piano_name':    sched.piano.name,
                    'piano_brand':   sched.piano.brand,
                    'piano_location': sched.piano.location.name,
                    'piano_id':      sched.piano_id,
                    'schedule_id':   sched.id,
                    'interval_days': sched.interval_days,
                    'description':   sched.task_name,
                })
            occ += timedelta(days=sched.interval_days)

    events.sort(key=lambda e: e['date'])
    return Response(events)
