from datetime import date, timedelta

from django.contrib.auth import authenticate
from rest_framework import viewsets, status, filters as drf_filters
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Location, Piano, MaintenanceSchedule, ScheduleTemplate, WorkOrder, MaintenanceLog, Technician, Photo
from .serializers import (
    LocationSerializer,
    PianoSerializer,
    MaintenanceScheduleSerializer,
    ScheduleTemplateSerializer,
    WorkOrderSerializer,
    MaintenanceLogSerializer,
    TechnicianMinimalSerializer,
    PhotoSerializer,
)


class LocationViewSet(viewsets.ModelViewSet):
    serializer_class = LocationSerializer

    def get_queryset(self):
        return Location.objects.prefetch_related('pianos').order_by('name')


class PianoViewSet(viewsets.ModelViewSet):
    queryset = Piano.objects.select_related('location').prefetch_related('photos').order_by('location__name', 'name')
    serializer_class = PianoSerializer

    # Filtering: GET /api/pianos/?location=3&piano_type=Grand
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_fields  = ['location', 'piano_type']
    # Search: GET /api/pianos/?search=steinway  (matches name, brand, serial_number)
    search_fields     = ['name', 'brand', 'serial_number']
    ordering_fields   = ['name', 'brand', 'piano_type', 'location__name', 'year_built', 'year_acquired']

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx


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


class WorkOrderViewSet(viewsets.ModelViewSet):
    serializer_class = WorkOrderSerializer

    filter_backends   = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_fields  = ['status', 'priority', 'order_type', 'piano', 'assigned_tech']
    search_fields     = ['description', 'piano__name']
    ordering_fields   = ['due_date', 'created_at', 'priority', 'status']
    ordering          = ['-due_date']

    def get_queryset(self):
        return WorkOrder.objects.select_related(
            'piano__location', 'assigned_tech', 'schedule'
        ).order_by('-due_date')

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
        wo = self.get_object()
        if wo.status in ('Complete', 'Cancelled'):
            return Response({'error': f'Work order is already {wo.status}.'}, status=status.HTTP_400_BAD_REQUEST)
        hours_worked    = request.data.get('hours_worked')
        work_performed  = request.data.get('work_performed')
        if not hours_worked or not work_performed:
            return Response({'error': 'hours_worked and work_performed are required.'}, status=status.HTTP_400_BAD_REQUEST)
        log = MaintenanceLog.objects.create(
            work_order=wo,
            technician=request.user,
            piano=wo.piano,
            hours_worked=hours_worked,
            work_performed=work_performed,
            notes=request.data.get('notes', ''),
        )
        wo.status = 'Complete'
        wo.completed_date = date.today()
        wo.save()
        return Response({
            'work_order': WorkOrderSerializer(wo).data,
            'log':        MaintenanceLogSerializer(log).data,
        })


class MaintenanceLogViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceLogSerializer

    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ['work_order']

    def get_queryset(self):
        return MaintenanceLog.objects.select_related('work_order__piano', 'technician').order_by('-logged_at')

    def perform_create(self, serializer):
        serializer.save(technician=self.request.user)


class TechnicianViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Technician.objects.filter(is_active=True).order_by('first_name', 'last_name')
    serializer_class = TechnicianMinimalSerializer


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

    # Piano detail
    piano_data = PianoSerializer(piano, context={'request': request}).data

    # Work orders for this piano
    work_orders = WorkOrder.objects.select_related('assigned_tech').filter(
        piano=piano
    ).order_by('-created_at')[:50]
    wo_data = WorkOrderSerializer(work_orders, many=True).data

    # Active schedules for this piano
    schedules = MaintenanceSchedule.objects.filter(piano=piano, is_active=True)
    sched_data = MaintenanceScheduleSerializer(schedules, many=True).data

    # Photos
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
