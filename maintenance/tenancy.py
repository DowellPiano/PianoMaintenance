from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied

from .models import Company, CompanyMembership, Technician


ACTIVE_COMPANY_SESSION_KEY = "active_company_id"


@dataclass(frozen=True)
class CompanyAccess:
    company: Company | None
    membership: CompanyMembership | None

    @property
    def can_admin(self) -> bool:
        return bool(self.membership and self.membership.role_admin and self.membership.is_active)

    @property
    def can_technician(self) -> bool:
        return bool(self.membership and self.membership.role_technician and self.membership.is_active)


def active_memberships_for_user(user: Technician):
    return user.active_company_memberships().order_by("company__name")


def resolve_active_company_access(user: Technician, session_company_id: int | None) -> CompanyAccess:
    memberships = list(active_memberships_for_user(user))
    if not memberships:
        return CompanyAccess(company=None, membership=None)

    membership = None
    if session_company_id:
        membership = next(
            (item for item in memberships if item.company_id == session_company_id),
            None,
        )
    if membership is None:
        membership = memberships[0]
    return CompanyAccess(company=membership.company, membership=membership)


def company_users(company: Company, *, admins_only=False, technicians_only=False):
    memberships = CompanyMembership.objects.filter(
        company=company,
        is_active=True,
        user__is_active=True,
    )
    if admins_only:
        memberships = memberships.filter(role_admin=True)
    if technicians_only:
        memberships = memberships.filter(role_technician=True)
    return Technician.objects.filter(company_memberships__in=memberships).distinct()


def company_queryset(queryset, company: Company):
    return queryset.filter(company=company)


def ensure_company_access(request):
    if not getattr(request, "active_company", None):
        raise PermissionDenied("No active company selected for this account.")
    return request.active_company
