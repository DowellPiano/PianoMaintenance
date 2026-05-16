from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from .models import CompanySettings, Technician


def _notifications_enabled():
    return (
        settings.EMAIL_NOTIFICATIONS_ENABLED
        and settings.EMAIL_HOST_USER
        and settings.EMAIL_HOST_PASSWORD
    )


def _unique_recipients(recipients):
    seen = set()
    unique = []
    for email in recipients:
        email = (email or '').strip()
        if email and email.lower() not in seen:
            seen.add(email.lower())
            unique.append(email)
    return unique


def _admin_recipients():
    recipients = list(
        Technician.objects.filter(
            is_active=True,
            role_admin=True,
        ).exclude(email='').values_list('email', flat=True)
    )
    company_email = CompanySettings.load().email
    return _unique_recipients([company_email, *recipients])


def _absolute_url(request, path):
    if request is None:
        return path
    return request.build_absolute_uri(path)


def _send_notification(subject, body, recipients):
    recipients = _unique_recipients(recipients)
    if not _notifications_enabled() or not recipients:
        return 0

    return send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        recipients,
        fail_silently=True,
    )


def notify_signup_request(user, request=None):
    if not _notifications_enabled():
        return 0

    url = _absolute_url(request, reverse('technician_list'))
    subject = f'New Piano Maintainer account request: {user.username}'
    body = (
        f'{user.get_full_name() or user.username} requested access to Piano Maintainer.\n\n'
        f'Username: {user.username}\n'
        f'Email: {user.email or "Not provided"}\n\n'
        f'Review technicians: {url}'
    )
    return _send_notification(subject, body, _admin_recipients())


def notify_maintenance_request(maintenance_request, work_order, request=None):
    if not _notifications_enabled():
        return 0

    piano_name = maintenance_request.piano.name if maintenance_request.piano else maintenance_request.piano_display
    url = _absolute_url(request, reverse('workorder_detail', args=[work_order.pk]))
    subject = f'New maintenance request for {piano_name}'
    body = (
        f'A public maintenance request created WO-{work_order.pk}.\n\n'
        f'Piano: {piano_name}\n'
        f'Reported by: {maintenance_request.reported_by_name or "Not provided"}\n'
        f'Reporter email: {maintenance_request.reported_by_email or "Not provided"}\n\n'
        f'Issue:\n{maintenance_request.issue_description}\n\n'
        f'Open work order: {url}'
    )
    return _send_notification(subject, body, _admin_recipients())


def notify_work_order_assigned(work_order, request=None):
    if not _notifications_enabled():
        return 0

    if not work_order.assigned_tech or not work_order.assigned_tech.email:
        return 0

    piano_name = work_order.piano.name if work_order.piano else work_order.piano_name
    url = _absolute_url(request, reverse('workorder_detail', args=[work_order.pk]))
    subject = f'WO-{work_order.pk} assigned to you'
    body = (
        f'WO-{work_order.pk} has been assigned to you.\n\n'
        f'Piano: {piano_name}\n'
        f'Type: {work_order.task_type or work_order.order_type}\n'
        f'Priority: {work_order.priority}\n'
        f'Due: {work_order.due_date or "No due date"}\n\n'
        f'Description:\n{work_order.description or "No description provided."}\n\n'
        f'Open work order: {url}'
    )
    return _send_notification(subject, body, [work_order.assigned_tech.email])
