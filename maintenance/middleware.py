from .tenancy import (
    ACTIVE_COMPANY_SESSION_KEY,
    active_memberships_for_user,
    resolve_active_company_access,
)


class ActiveCompanyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_company = None
        request.active_membership = None
        request.company_access = None
        request.available_companies = []

        if request.user.is_authenticated:
            memberships = list(active_memberships_for_user(request.user))
            session_company_id = request.session.get(ACTIVE_COMPANY_SESSION_KEY)
            access = resolve_active_company_access(
                request.user,
                session_company_id,
                memberships=memberships,
            )
            request.active_company = access.company
            request.active_membership = access.membership
            request.company_access = access
            request.available_companies = memberships
            if access.company and session_company_id != access.company.pk:
                request.session[ACTIVE_COMPANY_SESSION_KEY] = access.company.pk

        return self.get_response(request)
