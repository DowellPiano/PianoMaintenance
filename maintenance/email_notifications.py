from django.conf import settings
from django.core.mail import EmailMessage
from django.urls import reverse

from .models import CompanySettings
from .tenancy import company_users


def _notifications_enabled():
    return settings.EMAIL_NOTIFICATIONS_ENABLED


def _unique_recipients(recipients):
    seen = set()
    unique = []
    for email in recipients:
        email = (email or '').strip()
        if email and email.lower() not in seen:
            seen.add(email.lower())
            unique.append(email)
    return unique


def _admin_recipients(company):
    recipients = list(
        company_users(company, admins_only=True)
        .exclude(email='')
        .values_list('email', flat=True)
    )
    company_email = CompanySettings.load_for_company(company).email
    return _unique_recipients([company_email, *recipients])


def _absolute_url(request, path):
    if request is None:
        return path
    return request.build_absolute_uri(path)


def _send_notification(subject, body, recipients, reply_to=None):
    recipients = _unique_recipients(recipients)
    if not _notifications_enabled() or not recipients:
        return 0

    message = EmailMessage(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        recipients,
        reply_to=_unique_recipients(reply_to or []),
    )
    return message.send(fail_silently=True)


def notify_maintenance_request(maintenance_request, work_order, request=None):
    if not _notifications_enabled():
        return 0

    company = maintenance_request.company
    piano_name = maintenance_request.piano.name if maintenance_request.piano else maintenance_request.piano_display
    url = _absolute_url(request, reverse('workorder_detail', args=[work_order.pk]))
    admin_subject = f'New service request for {piano_name}'
    admin_body = (
        f'A public service request created WO-{work_order.pk}.\n\n'
        f'Company: {company.name}\n'
        f'Piano: {piano_name}\n'
        f'Reported by: {maintenance_request.reported_by_name or "Not provided"}\n'
        f'Reporter email: {maintenance_request.reported_by_email or "Not provided"}\n\n'
        f'Issue:\n{maintenance_request.issue_description}\n\n'
        f'Open work order: {url}'
    )
    admin_recipients = _admin_recipients(company)
    sent_count = _send_notification(
        admin_subject,
        admin_body,
        admin_recipients,
        reply_to=[maintenance_request.reported_by_email],
    )

    if maintenance_request.reported_by_email:
        requester_subject = f'We received your service request for {piano_name}'
        requester_body = (
            f'Thanks for letting us know about {piano_name}.\n\n'
            f'We received your service request and created WO-{work_order.pk}. '
            f'Our team will review it and follow up if needed.\n\n'
            f'Issue submitted:\n{maintenance_request.issue_description}\n\n'
            'You can reply to this email if you need to add more details.'
        )
        sent_count += _send_notification(
            requester_subject,
            requester_body,
            [maintenance_request.reported_by_email],
            reply_to=admin_recipients or [settings.DEFAULT_FROM_EMAIL],
        )

    return sent_count


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
        f'Company: {work_order.company.name}\n'
        f'Piano: {piano_name}\n'
        f'Type: {work_order.task_type or work_order.order_type}\n'
        f'Priority: {work_order.priority}\n'
        f'Due: {work_order.due_date or "No due date"}\n\n'
        f'Description:\n{work_order.description or "No description provided."}\n\n'
        f'Open work order: {url}'
    )
    return _send_notification(subject, body, [work_order.assigned_tech.email])
