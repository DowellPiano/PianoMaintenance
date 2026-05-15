from .tenancy import ACTIVE_COMPANY_SESSION_KEY, resolve_active_company_access


class ActiveCompanyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_company = None
        request.active_membership = None
        request.company_access = None
        request.available_companies = []

        if request.user.is_authenticated:
            access = resolve_active_company_access(
                request.user,
                request.session.get(ACTIVE_COMPANY_SESSION_KEY),
            )
            request.active_company = access.company
            request.active_membership = access.membership
            request.company_access = access
            request.available_companies = list(
                request.user.company_memberships.filter(
                    is_active=True,
                    company__is_active=True,
                ).select_related("company").order_by("company__name")
            )
            if access.company:
                request.session[ACTIVE_COMPANY_SESSION_KEY] = access.company.pk

        return self.get_response(request)
