from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse

from .models import Piano, MaintenanceRequest, WorkOrder


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
