def active_company(request):
    return {
        "active_company": getattr(request, "active_company", None),
        "active_membership": getattr(request, "active_membership", None),
        "available_companies": getattr(request, "available_companies", []),
        "company_access": getattr(request, "company_access", None),
    }
