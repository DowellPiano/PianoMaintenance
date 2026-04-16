"""
Views for the maintenance app.

All views except maintenance_request_view require the user to be logged in.
Login is enforced via the @login_required decorator, which redirects to
settings.LOGIN_URL when an unauthenticated user hits a protected page.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .models import MaintenanceRequest, Piano, WorkOrder


# ---------------------------------------------------------------------------
# Public — QR-code maintenance request
# ---------------------------------------------------------------------------
def maintenance_request_view(request, token):
    """
    Anyone can scan a piano's QR code and submit a maintenance request.
    No login required.
    The URL token maps 1-to-1 with Piano.qr_code_token.
    """
    piano = get_object_or_404(Piano, qr_code_token=token)

    if request.method == "POST":
        MaintenanceRequest.objects.create(
            piano=piano,
            reported_by_name=request.POST.get("reported_by_name", "").strip(),
            reported_by_email=request.POST.get("reported_by_email", "").strip(),
            issue_description=request.POST.get("issue_description", "").strip(),
        )
        return render(request, "maintenance/request_submitted.html", {"piano": piano})

    return render(request, "maintenance/maintenance_request.html", {"piano": piano})


# ---------------------------------------------------------------------------
# Protected views (login required)
# ---------------------------------------------------------------------------
@login_required
def dashboard(request):
    """Simple dashboard showing open work-order counts."""
    open_orders = WorkOrder.objects.filter(
        status__in=[WorkOrder.Status.OPEN, WorkOrder.Status.IN_PROGRESS]
    ).select_related("piano", "assigned_tech")[:10]

    new_requests = MaintenanceRequest.objects.filter(
        status=MaintenanceRequest.RequestStatus.NEW
    ).select_related("piano")[:10]

    context = {
        "open_orders": open_orders,
        "new_requests": new_requests,
    }
    return render(request, "maintenance/dashboard.html", context)


@login_required
def piano_list(request):
    """List all pianos, grouped by location."""
    pianos = Piano.objects.select_related("location").order_by("location__name", "name")
    return render(request, "maintenance/piano_list.html", {"pianos": pianos})


@login_required
def piano_detail(request, pk):
    """Detail view for a single piano — shows logs, schedules, open WOs."""
    piano = get_object_or_404(
        Piano.objects.select_related("location").prefetch_related(
            "schedules", "work_orders", "logs", "condition_readings"
        ),
        pk=pk,
    )
    return render(request, "maintenance/piano_detail.html", {"piano": piano})


@login_required
def work_order_list(request):
    """List work orders, filterable by status via ?status= query param."""
    status_filter = request.GET.get("status", "")
    qs = WorkOrder.objects.select_related("piano", "assigned_tech")

    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(
        request,
        "maintenance/work_order_list.html",
        {
            "work_orders": qs,
            "status_filter": status_filter,
            "status_choices": WorkOrder.Status.choices,
        },
    )


@login_required
def work_order_detail(request, pk):
    """Detail view for a single work order."""
    work_order = get_object_or_404(
        WorkOrder.objects.select_related("piano", "assigned_tech", "schedule").prefetch_related(
            "logs__parts_used__part",
            "logs__condition_readings",
            "maintenance_requests",
        ),
        pk=pk,
    )
    return render(
        request, "maintenance/work_order_detail.html", {"work_order": work_order}
    )
