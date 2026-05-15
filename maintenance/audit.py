from .models import AuditLog


EVENT_LABELS = {
    "piano.created": "Created",
    "piano.updated": "Updated",
    "piano.deactivated": "Deactivated",
    "organization.created": "Created",
    "organization.updated": "Updated",
    "organization.deleted": "Deleted",
    "venue.created": "Created",
    "venue.updated": "Updated",
    "venue.deleted": "Deleted",
    "workorder.created": "Created",
    "workorder.updated": "Updated",
    "workorder.assigned": "Assignment changed",
    "workorder.completed": "Completed",
    "workorder.reopened": "Reopened",
    "workorder.work_logged": "Work logged",
    "workorder.deleted": "Deleted",
    "membership.created": "Membership created",
    "membership.updated": "Membership updated",
    "membership.activated": "Membership activated",
    "membership.deactivated": "Membership deactivated",
    "invitation.created": "Invitation sent",
    "invitation.revoked": "Invitation revoked",
    "invitation.resent": "Invitation resent",
    "company_settings.updated": "Settings updated",
    "part.created": "Created",
    "part.updated": "Updated",
    "maintenance_request.approved": "Approved",
    "maintenance_request.rejected": "Rejected",
    "piano.photo_uploaded": "Photo uploaded",
    "piano.photo_deleted": "Photo deleted",
    "piano.imported": "Pianos imported",
    "report.workorders_exported": "Work orders exported",
    "report.pianos_exported": "Pianos exported",
}


def log_audit_event(*, company, actor=None, event_type, target=None, message="", metadata=None):
    target_model = ""
    target_id = ""
    if target is not None:
        target_model = target._meta.label
        target_id = str(target.pk)

    return AuditLog.objects.create(
        company=company,
        actor=actor,
        event_type=event_type,
        target_model=target_model,
        target_id=target_id,
        message=message,
        metadata=metadata or {},
    )


def event_label(event_type):
    return EVENT_LABELS.get(event_type, event_type.replace(".", " ").replace("_", " ").title())


def target_audit_events(*, company, target, limit=5):
    if target is None or target.pk is None:
        return []

    logs = (
        AuditLog.objects
        .filter(
            company=company,
            target_model=target._meta.label,
            target_id=str(target.pk),
        )
        .select_related("actor")
        .order_by("-created_at")[:limit]
    )

    events = []
    for log in logs:
        actor_name = "System"
        if log.actor:
            actor_name = log.actor.get_full_name() or log.actor.username
        events.append({
            "label": event_label(log.event_type),
            "actor_name": actor_name,
            "created_at": log.created_at,
            "message": log.message,
            "metadata": log.metadata,
        })
    return events
