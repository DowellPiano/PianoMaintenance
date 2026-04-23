import csv
from datetime import date

from django.db.models import Count, Max, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Attachment,
    Location,
    MaintenanceLog,
    MaintenanceSchedule,
    Piano,
    ScheduleTemplate,
    Technician,
    WorkOrder,
)
from .serializers import (
    AttachmentSerializer,
    LocationSerializer,
    MaintenanceLogSerializer,
    MaintenanceScheduleSerializer,
    PianoSerializer,
    ScheduleTemplateSerializer,
    TechnicianSerializer,
    WorkOrderSerializer,
)


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------
class LocationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Location.objects.all().order_by('name')
    serializer_class = LocationSerializer


# ---------------------------------------------------------------------------
# Piano  (soft-delete via is_active flag)
# ---------------------------------------------------------------------------
class PianoViewSet(viewsets.ModelViewSet):
    serializer_class = PianoSerializer

    def get_queryset(self):
        qs = Piano.objects.select_related('location').order_by('location__name', 'name')
        # ?active=false → inactive only  |  ?active=all → everything  |  default → active only
        active_param = self.request.query_params.get('active', 'true').lower()
        if active_param == 'false':
            return qs.filter(is_active=False)
        elif active_param == 'all':
            return qs
        return qs.filter(is_active=True)

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
# Technician  (Bug 4: reactivate / deactivate actions)
# ---------------------------------------------------------------------------
class TechnicianViewSet(viewsets.ModelViewSet):
    serializer_class = TechnicianSerializer

    def get_queryset(self):
        return Technician.objects.all().order_by('last_name', 'first_name')

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

    def get_queryset(self):
        return MaintenanceSchedule.objects.select_related(
            'piano__location', 'template'
        ).order_by('piano__location__name', 'piano__name', 'task_type')


# ---------------------------------------------------------------------------
# WorkOrder  (Bug 2: full CRUD + complete action)
# ---------------------------------------------------------------------------
class WorkOrderViewSet(viewsets.ModelViewSet):
    serializer_class = WorkOrderSerializer

    def get_queryset(self):
        qs = WorkOrder.objects.select_related(
            'piano', 'assigned_tech', 'schedule'
        ).order_by('-created_at')
        piano_id = self.request.query_params.get('piano')
        if piano_id:
            qs = qs.filter(piano_id=piano_id)
        return qs

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        work_order = self.get_object()

        # --- Validate hours_worked ---
        try:
            hours_worked = float(request.data.get('hours_worked', 0))
        except (TypeError, ValueError):
            hours_worked = 0
        if hours_worked <= 0:
            return Response(
                {'error': 'hours_worked must be a positive number.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        work_performed = request.data.get('work_performed', '').strip()
        if not work_performed:
            return Response(
                {'error': 'work_performed is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        notes = request.data.get('notes', '')

        # --- Resolve technician ---
        if request.user and request.user.is_authenticated:
            technician = request.user
        elif work_order.assigned_tech:
            technician = work_order.assigned_tech
        else:
            return Response(
                {'error': 'No technician could be determined. Assign a technician or authenticate.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Create MaintenanceLog ---
        log = MaintenanceLog.objects.create(
            work_order=work_order,
            technician=technician,
            piano=work_order.piano,
            hours_worked=hours_worked,
            work_performed=work_performed,
            notes=notes,
        )

        # --- Close the work order ---
        today = date.today()
        work_order.status = WorkOrder.Status.COMPLETE
        work_order.completed_date = today
        work_order.save(update_fields=['status', 'completed_date'])

        # --- Update schedule's last_service_date (Bug 3) ---
        if work_order.schedule_id:
            MaintenanceSchedule.objects.filter(pk=work_order.schedule_id).update(
                last_service_date=today
            )

        return Response({
            'work_order': WorkOrderSerializer(work_order).data,
            'log_id': log.pk,
        })


# ---------------------------------------------------------------------------
# Attachment  (Bug 6)
# ---------------------------------------------------------------------------
class AttachmentViewSet(viewsets.ModelViewSet):
    serializer_class = AttachmentSerializer

    def get_queryset(self):
        qs = Attachment.objects.select_related('piano', 'work_order').order_by('-uploaded_at')
        piano_id = self.request.query_params.get('piano')
        work_order_id = self.request.query_params.get('work_order')
        if piano_id:
            qs = qs.filter(piano_id=piano_id)
        if work_order_id:
            qs = qs.filter(work_order_id=work_order_id)
        return qs


# ---------------------------------------------------------------------------
# Reports  (Bug 5: technician report + CSV exports)
# ---------------------------------------------------------------------------
class ReportsViewSet(viewsets.ViewSet):
    """
    Reporting endpoints. No model backing — all data is aggregated on-the-fly.

    GET /api/reports/technicians/              — all-technician workload summary
    GET /api/reports/technicians/export_csv/   — same data as CSV download
    GET /api/reports/pianos/export_csv/        — piano service status CSV
    """

    def _build_log_filter(self, request):
        """Return a Q object / filter kwargs for date range if supplied."""
        from django.db.models import Q
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
                    0,
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
                    0,
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
        from datetime import timedelta
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
            # Use the soonest-due active schedule for "next due"
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

    # ------------------------------------------------------------------
    # Internal helper: convert filter kwargs dict → Q object
    # ------------------------------------------------------------------
    @staticmethod
    def _q(filter_dict):
        from django.db.models import Q
        q = Q()
        for key, val in filter_dict.items():
            q &= Q(**{key: val})
        return q
