import csv
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import authenticate
from django.db.models import Count, DecimalField, F, Max, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, status, filters as drf_filters
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    Location, Piano, MaintenanceSchedule, ScheduleTemplate,
    WorkOrder, MaintenanceLog, Technician, Team, Photo,
    ConditionReading, Part, PartUsed, MaintenanceRequest, Alert,
)
from .serializers import (
    AttachmentSerializer,
    ConditionReadingSerializer,
    LocationSerializer,
    MaintenanceLogSerializer,
    MaintenanceScheduleSerializer,
    PianoSerializer,
    ScheduleTemplateSerializer,
    WorkOrderSerializer,
    TechnicianMinimalSerializer,
    TechnicianSerializer,
    TeamSerializer,
    PhotoSerializer,
    PartSerializer,
    PartUsedSerializer,
    MaintenanceRequestSerializer,
    AlertSerializer,
)


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------
class LocationViewSet(viewsets.ModelViewSet):
    serializer_class = LocationSerializer

    def get_queryset(self):
        return Location.objects.prefetch_related('pianos').order_by('name')


# ---------------------------------------------------------------------------
# Piano  (soft-delete via is_active flag)
# ---------------------------------------------------------------------------
class PianoViewSet(viewsets.ModelViewSet):
    serializer_class = PianoSerializer

    # Filtering: GET /api/pianos/?location=3&piano_type=Grand
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_fields  = ['location', 'piano_type']
    # Search: GET /api/pianos/?search=steinway  (matches name, brand, serial_number)
    search_fields     = ['name', 'brand', 'serial_number']
    ordering_fields   = ['name', 'brand', 'piano_type', 'location__name', 'year_built', 'year_acquired']

    def get_queryset(self):
        qs = Piano.objects.select_related('location').prefetch_related('photos').order_by('location__name', 'name')
        # ?active=false → inactive only  |  ?active=all → everything  |  default → active only
        active_param = self.request.query_params.get('active', 'true').lower()
        if active_param == 'false':
            return qs.filter(is_active=False)
        elif active_param == 'all':
            return qs
        return qs.filter(is_active=True)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    def get_object(self):
        """Always look up by pk without the is_active filter so destroy/reactivate work on inactive pianos."""
        queryset = Piano.objects.select_related('location')
        obj = get_object_or_404(queryset, pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, obj)
        return obj

    def destroy(self, request, *args, **kwargs):
        """Soft-delete: set is_active=False instead of removing from the DB."""
        piano = self.get_object()
        Piano.objects.filter(pk=piano.pk).update(is_active=False)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def reactivate(self, request, pk=None):
        """Reactivate a previously deactivated piano."""
        piano = self.get_object()
        Piano.objects.filter(pk=piano.pk).update(is_active=True)
        piano.refresh_from_db()
        return Response(self.get_serializer(piano).data)


# ---------------------------------------------------------------------------
# Technician  (reactivate / deactivate actions)
# ---------------------------------------------------------------------------
class IsStaffPermission(IsAuthenticated):
    """Extends IsAuthenticated: also requires is_staff=True."""
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_staff


class TechnicianViewSet(viewsets.ModelViewSet):
    queryset = Technician.objects.all().order_by('last_name', 'first_name')

    def get_serializer_class(self):
        if self.action in ('list', 'retrieve'):
            return TechnicianMinimalSerializer
        return TechnicianSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAuthenticated(), IsStaffPermission()]
        return [IsAuthenticated()]

    def destroy(self, request, *args, **kwargs):
        technician = self.get_object()
        has_work_orders = WorkOrder.objects.filter(assigned_tech=technician).exists()
        has_logs        = MaintenanceLog.objects.filter(technician=technician).exists()
        if has_work_orders or has_logs:
            return Response(
                {'error': 'Cannot delete technician with linked work orders or logs. Deactivate instead.'},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def reactivate(self, request, pk=None):
        # Fetch without filter_queryset so inactive users are never silently 404'd.
        technician = get_object_or_404(Technician, pk=pk)
        self.check_object_permissions(request, technician)
        # Direct queryset UPDATE bypasses AbstractUser.save() side-effects.
        Technician.objects.filter(pk=technician.pk).update(is_active=True)
        # Reload from DB so the response reflects actual persisted state.
        technician.refresh_from_db()
        return Response(TechnicianSerializer(technician).data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        technician = get_object_or_404(Technician, pk=pk)
        self.check_object_permissions(request, technician)
        Technician.objects.filter(pk=technician.pk).update(is_active=False)
        technician.refresh_from_db()
        return Response(TechnicianSerializer(technician).data)


# ---------------------------------------------------------------------------
# TeamViewSet
# ---------------------------------------------------------------------------
class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.select_related('manager').order_by('name')
    serializer_class = TeamSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAuthenticated(), IsStaffPermission()]
        return [IsAuthenticated()]

    def retrieve(self, request, *args, **kwargs):
        team = self.get_object()
        data = TeamSerializer(team).data
        members = team.members.all().order_by('first_name', 'last_name')
        data['members'] = [
            {
                'id':        m.id,
                'username':  m.username,
                'full_name': m.get_full_name() or m.username,
                'is_active': m.is_active,
            }
            for m in members
        ]
        return Response(data)


# ---------------------------------------------------------------------------
# ScheduleTemplate
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# MaintenanceSchedule
# ---------------------------------------------------------------------------
class MaintenanceScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceScheduleSerializer

    # Filtering: GET /api/schedules/?piano=5&is_active=true&task_type=Tuning
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_fields  = ['piano', 'is_active', 'task_type']
    # Search: GET /api/schedules/?search=tuning  (matches task_name and piano name)
    search_fields     = ['task_name', 'piano__name']
    ordering_fields   = ['piano__name', 'task_type', 'interval_days']

    def get_queryset(self):
        return MaintenanceSchedule.objects.select_related(
            'piano__location', 'template'
        ).order_by('piano__location__name', 'piano__name', 'task_type')


# ---------------------------------------------------------------------------
# WorkOrder
# ---------------------------------------------------------------------------
class WorkOrderViewSet(viewsets.ModelViewSet):
    serializer_class = WorkOrderSerializer

    filter_backends   = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_fields  = ['status', 'priority', 'order_type', 'piano', 'assigned_tech']
    search_fields     = ['description', 'piano__name']
    ordering_fields   = ['due_date', 'created_at', 'priority', 'status']
    ordering          = ['-due_date']

    def get_queryset(self):
        qs = WorkOrder.objects.select_related(
            'piano__location', 'assigned_tech', 'schedule'
        ).order_by('-due_date')
        piano_id = self.request.query_params.get('piano')
        if piano_id:
            qs = qs.filter(piano_id=piano_id)
        return qs

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        wo = self.get_object()
        if wo.status != 'Open':
            return Response({'error': 'Only Open work orders can be started.'}, status=status.HTTP_400_BAD_REQUEST)
        wo.status = 'In Progress'
        wo.save()
        return Response(WorkOrderSerializer(wo).data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        work_order = self.get_object()

        if work_order.status in ('Complete', 'Cancelled'):
            return Response(
                {'error': f'Work order is already {work_order.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        hours_worked   = request.data.get('hours_worked')
        work_performed = request.data.get('work_performed', '').strip()

        try:
            hours_worked_val = float(hours_worked)
        except (TypeError, ValueError):
            hours_worked_val = 0

        if hours_worked_val <= 0 or not work_performed:
            return Response(
                {'error': 'hours_worked must be greater than 0 and work_performed is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        notes = request.data.get('notes', '')

        # Resolve technician
        if request.user and request.user.is_authenticated:
            technician = request.user
        elif work_order.assigned_tech:
            technician = work_order.assigned_tech
        else:
            return Response(
                {'error': 'No technician could be determined. Assign a technician or authenticate.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log = MaintenanceLog.objects.create(
            work_order=work_order,
            technician=technician,
            piano=work_order.piano,
            hours_worked=hours_worked_val,
            work_performed=work_performed,
            notes=notes,
        )

        today_date = date.today()
        work_order.status = WorkOrder.Status.COMPLETE
        work_order.completed_date = today_date
        work_order.save(update_fields=['status', 'completed_date'])

        # Update schedule's last_service_date
        if work_order.schedule_id:
            MaintenanceSchedule.objects.filter(pk=work_order.schedule_id).update(
                last_service_date=today_date
            )

        return Response({
            'work_order': WorkOrderSerializer(work_order).data,
            'log':        MaintenanceLogSerializer(log).data,
        })


# ---------------------------------------------------------------------------
# MaintenanceLog
# ---------------------------------------------------------------------------
class MaintenanceLogViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceLogSerializer

    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ['work_order']

    def get_queryset(self):
        return MaintenanceLog.objects.select_related('work_order__piano', 'technician').order_by('-logged_at')

    def perform_create(self, serializer):
        serializer.save(technician=self.request.user)


# ---------------------------------------------------------------------------
# ConditionReadingViewSet
# ---------------------------------------------------------------------------
class ConditionReadingViewSet(viewsets.ModelViewSet):
    serializer_class = ConditionReadingSerializer

    filter_backends  = [DjangoFilterBackend, drf_filters.OrderingFilter]
    filterset_fields = ['piano', 'log']
    ordering_fields  = ['recorded_at']
    ordering         = ['-recorded_at']

    def get_queryset(self):
        qs = ConditionReading.objects.select_related('piano', 'log').order_by('-recorded_at')
        piano_id = self.request.query_params.get('piano')
        if piano_id:
            qs = qs.filter(piano_id=piano_id)
        return qs

    def perform_create(self, serializer):
        # Auto-derive piano from the linked log if not explicitly provided
        piano = serializer.validated_data.get('piano')
        if piano is None:
            log = serializer.validated_data.get('log')
            if log:
                piano = log.piano
        serializer.save(piano=piano)


# ---------------------------------------------------------------------------
# PartViewSet / PartUsedViewSet
# ---------------------------------------------------------------------------
class PartViewSet(viewsets.ModelViewSet):
    serializer_class = PartSerializer

    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    search_fields   = ['name', 'part_number']
    ordering_fields = ['name', 'stock_quantity']
    ordering        = ['name']

    def get_queryset(self):
        qs = Part.objects.all().order_by('name')
        needs_reorder = self.request.query_params.get('needs_reorder')
        if needs_reorder is not None:
            if needs_reorder.lower() in ('true', '1'):
                qs = qs.filter(stock_quantity__lte=F('reorder_threshold'))
            else:
                qs = qs.exclude(stock_quantity__lte=F('reorder_threshold'))
        return qs


class PartUsedViewSet(viewsets.ModelViewSet):
    serializer_class = PartUsedSerializer

    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ['log']

    def get_queryset(self):
        return PartUsed.objects.select_related('log', 'part').order_by('-id')

    def perform_create(self, serializer):
        part          = serializer.validated_data['part']
        quantity_used = serializer.validated_data['quantity_used']
        cost_at_time  = serializer.validated_data.get('cost_at_time')

        # Auto-fill cost from part.unit_cost if not provided
        if cost_at_time is None:
            cost_at_time = part.unit_cost

        instance = serializer.save(cost_at_time=cost_at_time)

        # Decrement stock
        Part.objects.filter(pk=part.pk).update(
            stock_quantity=part.stock_quantity - quantity_used
        )
        return instance


# ---------------------------------------------------------------------------
# MaintenanceRequestViewSet
# ---------------------------------------------------------------------------
class MaintenanceRequestViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceRequestSerializer

    filter_backends  = [DjangoFilterBackend, drf_filters.OrderingFilter]
    filterset_fields = ['status', 'piano']
    ordering_fields  = ['created_at']
    ordering         = ['-created_at']

    def get_queryset(self):
        return MaintenanceRequest.objects.select_related(
            'piano', 'work_order', 'work_order__assigned_tech'
        ).order_by('-created_at')

    def perform_create(self, serializer):
        mr = serializer.save(status='Assigned')
        wo = WorkOrder.objects.create(
            piano=mr.piano,
            order_type=WorkOrder.OrderType.REQUEST,
            status=WorkOrder.Status.OPEN,
            priority=WorkOrder.Priority.NORMAL,
            description=mr.issue_description,
        )
        mr.work_order = wo
        mr.save(update_fields=['work_order'])


# ---------------------------------------------------------------------------
# PhotoViewSet
# ---------------------------------------------------------------------------
class PhotoViewSet(viewsets.ModelViewSet):
    serializer_class = PhotoSerializer

    def get_queryset(self):
        qs = Photo.objects.all()
        piano_id = self.request.query_params.get('piano')
        work_order_id = self.request.query_params.get('work_order')
        if piano_id:
            qs = qs.filter(piano_id=piano_id)
        if work_order_id:
            qs = qs.filter(work_order_id=work_order_id)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    @action(detail=True, methods=['post'])
    def set_profile(self, request, pk=None):
        photo = self.get_object()
        if not photo.piano_id:
            return Response({'error': 'Photo is not linked to a piano.'}, status=400)
        # Unset all other profile photos for this piano
        Photo.objects.filter(piano_id=photo.piano_id, is_profile_photo=True).update(is_profile_photo=False)
        photo.is_profile_photo = True
        photo.save()
        return Response({'ok': True})


# ---------------------------------------------------------------------------
# AlertViewSet
# ---------------------------------------------------------------------------
class AlertViewSet(viewsets.ModelViewSet):
    serializer_class = AlertSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    filter_backends  = [DjangoFilterBackend, drf_filters.OrderingFilter]
    filterset_fields = ['alert_type']
    ordering         = ['-sent_at']

    def get_queryset(self):
        return (
            Alert.objects
            .filter(acknowledged=False)
            .select_related('work_order__piano__location')
            .order_by('-sent_at')
        )

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        alert.acknowledged = True
        alert.save()
        return Response(AlertSerializer(alert).data)


# ---------------------------------------------------------------------------
# Attachment  (legacy support)
# ---------------------------------------------------------------------------
class AttachmentViewSet(viewsets.ModelViewSet):
    serializer_class = AttachmentSerializer

    def get_queryset(self):
        qs = Photo.objects.all()
        piano_id = self.request.query_params.get('piano')
        work_order_id = self.request.query_params.get('work_order')
        if piano_id:
            qs = qs.filter(piano_id=piano_id)
        if work_order_id:
            qs = qs.filter(work_order_id=work_order_id)
        return qs


# ---------------------------------------------------------------------------
# Reports  (technician report + CSV exports)
# ---------------------------------------------------------------------------
class ReportsViewSet(viewsets.ViewSet):
    """
    Reporting endpoints. No model backing — all data is aggregated on-the-fly.

    GET /api/reports/technicians/              — all-technician workload summary
    GET /api/reports/technicians/export_csv/   — same data as CSV download
    GET /api/reports/pianos/export_csv/        — piano service status CSV
    """

    def _build_log_filter(self, request):
        """Return a filter kwargs dict for date range if supplied."""
        filters = {}
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            filters['logs__logged_at__date__gte'] = date_from
        if date_to:
            filters['logs__logged_at__date__lte'] = date_to
        return filters

    @action(detail=False, methods=['get'], url_path='technicians')
    def technicians(self, request):
        log_filters = self._build_log_filter(request)
        techs = (
            Technician.objects
            .annotate(
                total_hours=Coalesce(
                    Sum('logs__hours_worked', filter=self._q(log_filters)),
                    Decimal('0'),
                    output_field=DecimalField(),
                ),
                work_order_count=Count(
                    'logs__work_order',
                    distinct=True,
                    filter=self._q(log_filters),
                ),
                last_logged_at=Max(
                    'logs__logged_at',
                    filter=self._q(log_filters),
                ),
            )
            .order_by('last_name', 'first_name')
        )
        data = [
            {
                'id': t.pk,
                'name': t.get_full_name() or t.username,
                'total_hours': float(t.total_hours),
                'work_order_count': t.work_order_count,
                'last_logged_at': t.last_logged_at,
            }
            for t in techs
        ]
        return Response(data)

    @action(detail=False, methods=['get'], url_path='technicians/export_csv')
    def technicians_export_csv(self, request):
        log_filters = self._build_log_filter(request)
        techs = (
            Technician.objects
            .annotate(
                total_hours=Coalesce(
                    Sum('logs__hours_worked', filter=self._q(log_filters)),
                    Decimal('0'),
                    output_field=DecimalField(),
                ),
                work_order_count=Count(
                    'logs__work_order',
                    distinct=True,
                    filter=self._q(log_filters),
                ),
                last_logged_at=Max(
                    'logs__logged_at',
                    filter=self._q(log_filters),
                ),
            )
            .order_by('last_name', 'first_name')
        )
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="technician_report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Technician', 'Total Hours', 'Work Orders Completed', 'Last Activity'])
        for t in techs:
            writer.writerow([
                t.get_full_name() or t.username,
                float(t.total_hours),
                t.work_order_count,
                t.last_logged_at.strftime('%Y-%m-%d %H:%M') if t.last_logged_at else '',
            ])
        return response

    @action(detail=False, methods=['get'], url_path='pianos/export_csv')
    def pianos_export_csv(self, request):
        pianos = (
            Piano.objects
            .select_related('location')
            .prefetch_related('schedules', 'work_orders')
            .order_by('location__name', 'name')
        )
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="piano_report.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Piano', 'Location', 'Last Service Date', 'Next Due Date', 'Open Work Orders'
        ])
        today = date.today()
        for piano in pianos:
            open_wo_count = sum(
                1 for wo in piano.work_orders.all()
                if wo.status in (WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS)
            )
            next_due = None
            for sched in piano.schedules.all():
                if not sched.is_active:
                    continue
                anchor = sched.last_service_date
                if anchor is None:
                    anchor = piano.date_acquired or today
                candidate = anchor + timedelta(days=sched.interval_days)
                if next_due is None or candidate < next_due:
                    next_due = candidate

            last_service = max(
                (s.last_service_date for s in piano.schedules.all() if s.last_service_date),
                default=None,
            )
            writer.writerow([
                str(piano),
                piano.location.name,
                last_service.strftime('%Y-%m-%d') if last_service else '',
                next_due.strftime('%Y-%m-%d') if next_due else '',
                open_wo_count,
            ])
        return response

    @staticmethod
    def _q(filter_dict):
        from django.db.models import Q
        q = Q()
        for key, val in filter_dict.items():
            q &= Q(**{key: val})
        return q


# ---------------------------------------------------------------------------
# Function-based views
# ---------------------------------------------------------------------------

@api_view(['GET'])
def alert_unread_count(request):
    """GET /api/alerts/unread-count/ — counts of unacknowledged alerts by type."""
    base = Alert.objects.filter(acknowledged=False)
    overdue  = base.filter(alert_type=Alert.AlertType.OVERDUE).count()
    due_soon = base.filter(alert_type=Alert.AlertType.DUE_SOON).count()
    return Response({
        'overdue':  overdue,
        'due_soon': due_soon,
        'total':    overdue + due_soon,
    })


@api_view(['GET'])
def dashboard_stats(request):
    today = date.today()
    active_statuses = ('Open', 'In Progress')
    month_start = today.replace(day=1)

    open_count      = WorkOrder.objects.filter(status='Open').count()
    in_progress     = WorkOrder.objects.filter(status='In Progress').count()
    overdue         = WorkOrder.objects.filter(due_date__lt=today).exclude(status__in=('Complete', 'Cancelled')).count()
    due_soon        = WorkOrder.objects.filter(
        due_date__gte=today, due_date__lte=today + timedelta(days=7)
    ).exclude(status__in=('Complete', 'Cancelled')).count()
    completed_month = WorkOrder.objects.filter(
        status='Complete', completed_date__gte=month_start, completed_date__lte=today
    ).count()

    urgent_qs = WorkOrder.objects.select_related('piano__location', 'assigned_tech').filter(
        status__in=active_statuses
    ).order_by('due_date')[:10]
    urgent_open = [
        {
            'id':               wo.id,
            'piano_name':       wo.piano.name,
            'piano_location':   wo.piano.location.name,
            'order_type':       wo.order_type,
            'priority':         wo.priority,
            'status':           wo.status,
            'due_date':         wo.due_date,
            'assigned_tech_name': wo.assigned_tech.get_full_name() if wo.assigned_tech else None,
        }
        for wo in urgent_qs
    ]

    return Response({
        'open':                open_count,
        'in_progress':         in_progress,
        'overdue':             overdue,
        'due_soon':            due_soon,
        'completed_this_month': completed_month,
        'urgent_open':         urgent_open,
    })


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
        'Open':        '#3b82f6',
        'In Progress': '#f59e0b',
        'Complete':    '#22c55e',
        'Cancelled':   '#9ca3af',
    }
    PRIORITY_DOT = {
        'Urgent': '🔴',
        'High':   '🟠',
        'Normal': '🔵',
        'Low':    '⚪',
    }
    today = date.today()
    for wo in work_orders:
        is_overdue = (
            wo.due_date is not None and
            wo.due_date < today and
            wo.status not in ('Complete', 'Cancelled')
        )
        events.append({
            'id':            f'wo_{wo.id}',
            'type':          'work_order',
            'title':         f'{wo.piano.name} — {wo.order_type}',
            'date':          str(wo.due_date),
            'status':        'Overdue' if is_overdue else wo.status,
            'priority':      wo.priority,
            'color':         '#ef4444' if is_overdue else STATUS_COLOR.get(wo.status, '#3b82f6'),
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


@api_view(['GET'])
def piano_profile(request, piano_id):
    """
    Returns enriched profile data for a single piano:
    piano detail, work_orders (last 50), schedules, photos
    """
    try:
        piano = Piano.objects.select_related('location').prefetch_related('photos').get(pk=piano_id)
    except Piano.DoesNotExist:
        return Response({'error': 'Piano not found.'}, status=404)

    piano_data = PianoSerializer(piano, context={'request': request}).data

    work_orders = WorkOrder.objects.select_related('assigned_tech').filter(
        piano=piano
    ).order_by('-created_at')[:50]
    wo_data = WorkOrderSerializer(work_orders, many=True).data

    schedules = MaintenanceSchedule.objects.filter(piano=piano, is_active=True)
    sched_data = MaintenanceScheduleSerializer(schedules, many=True).data

    photos = Photo.objects.filter(piano=piano)
    photo_data = PhotoSerializer(photos, many=True, context={'request': request}).data

    return Response({
        'piano':       piano_data,
        'work_orders': wo_data,
        'schedules':   sched_data,
        'photos':      photo_data,
    })


@api_view(['GET'])
def location_profile(request, location_id):
    """
    Returns enriched profile data for a single location:
    location detail + all pianos at that location (with profile photo URLs).
    """
    try:
        location = Location.objects.prefetch_related('pianos__photos').get(pk=location_id)
    except Location.DoesNotExist:
        return Response({'error': 'Location not found.'}, status=404)

    location_data = LocationSerializer(location).data

    pianos = location.pianos.prefetch_related('photos').order_by('name')
    piano_data = PianoSerializer(pianos, many=True, context={'request': request}).data

    return Response({
        'location': location_data,
        'pianos':   piano_data,
    })


# ── Authentication endpoints ────────────────────────────────────────────────

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def auth_login(request):
    """
    POST { username, password } → { token, user }
    The only endpoint that does not require an existing token.
    """
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '')
    user = authenticate(request, username=username, password=password)
    if not user:
        return Response({'error': 'Invalid username or password.'}, status=status.HTTP_401_UNAUTHORIZED)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({
        'token': token.key,
        'user': {
            'id':         user.id,
            'username':   user.username,
            'first_name': user.first_name,
            'last_name':  user.last_name,
            'email':      user.email,
            'is_staff':   user.is_staff,
        },
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def auth_logout(request):
    """
    POST (with token header) — deletes the token so it can no longer be used.
    """
    try:
        request.user.auth_token.delete()
    except Token.DoesNotExist:
        pass
    return Response({'ok': True})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def auth_me(request):
    """
    GET — returns the currently authenticated user's info.
    Useful for the frontend to restore session on page refresh.
    """
    user = request.user
    return Response({
        'id':         user.id,
        'username':   user.username,
        'first_name': user.first_name,
        'last_name':  user.last_name,
        'email':      user.email,
        'is_staff':   user.is_staff,
    })
