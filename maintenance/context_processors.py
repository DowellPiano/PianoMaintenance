def active_company(request):
    membership = getattr(request, "active_membership", None)
    tech_mode = bool(
        getattr(request, "user", None)
        and request.user.is_authenticated
        and membership
        and membership.is_active
        and membership.role_admin
        and membership.role_technician
        and request.session.get("tech_mode")
    )
    return {
        "active_company": getattr(request, "active_company", None),
        "active_membership": getattr(request, "active_membership", None),
        "available_companies": getattr(request, "available_companies", []),
        "company_access": getattr(request, "company_access", None),
        "tech_mode": tech_mode,
    }
