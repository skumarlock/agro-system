from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from core.services.currency import update_usd_rate  
from core.services import (
    get_dashboard_data,
    get_field_crop_report,
    get_field_crops_reports,
    get_season_report,
    get_user_field_crop_or_404,
    get_user_season_or_404,
)

@login_required
def dashboard_view(request):
    period = request.GET.get("period", "all")

    data = {
        "dashboard": get_dashboard_data(request.user, period=period),
        "user_role": request.user.role,
    }
    from core.services.currency import get_usd_rate
    data["usd_rate"] = get_usd_rate()

    currency = request.GET.get("currency", "uzs")
    data["currency"] = currency

    sort = request.GET.get("sort")
    order = request.GET.get("order", "asc")

    resources = data["dashboard"]["resources"]

    if sort:
        reverse = order == "desc"

        if sort == "name":
            resources = sorted(resources, key=lambda x: x["name"], reverse=reverse)
        elif sort == "quantity":
            resources = sorted(resources, key=lambda x: x["quantity"], reverse=reverse)
        elif sort == "cost":
            resources = sorted(resources, key=lambda x: x["cost"], reverse=reverse)

        next_order = "desc" if order == "asc" else "asc"
    else:
        next_order = "asc"

    # выделение топ ресурса
    if resources:
        max_cost = max(r["cost"] for r in resources)
        for r in resources:
            r["is_top"] = r["cost"] == max_cost

    data["dashboard"]["resources"] = resources
    data["sort"] = sort
    data["order"] = order
    data["next_order"] = next_order
    data["is_worker"] = request.user.role == "WORKER"
    data["is_owner"] = request.user.role == "OWNER"
    
    query_dict = request.GET.copy()
    query_dict.pop("currency", None)
    query_dict.pop("period", None)
    data["query_params"] = query_dict.urlencode()

    return render(request, "core/dashboard.html", data)


@login_required
def field_crop_list_view(request):
    data = {
        "field_crops": get_field_crops_reports(request.user)
    }
    return render(request, "core/field_crop_list.html", data)


@login_required
def field_crop_detail_view(request, pk):
    field_crop = get_user_field_crop_or_404(request.user, pk)

    data = {
        "report": get_field_crop_report(field_crop),
    }
    return render(request, "core/field_crop_detail.html", data)


@login_required
def season_report_view(request, pk):
    season = get_user_season_or_404(request.user, pk)

    data = {
        "report": get_season_report(season, request.user),
    }

    # --- СОРТИРОВКА (копия из dashboard) ---
    sort = request.GET.get("sort")
    order = request.GET.get("order", "asc")

    resources = data["report"]["resources"]

    if sort:
        reverse = order == "desc"

        if sort == "name":
            resources = sorted(resources, key=lambda x: x["name"], reverse=reverse)
        elif sort == "quantity":
            resources = sorted(resources, key=lambda x: x["quantity"], reverse=reverse)
        elif sort == "cost":
            resources = sorted(resources, key=lambda x: x["cost"], reverse=reverse)

        next_order = "desc" if order == "asc" else "asc"
    else:
        next_order = "asc"

    data["report"]["resources"] = resources
    data["sort"] = sort
    data["order"] = order
    data["next_order"] = next_order

    query_dict = request.GET.copy()
    data["query_params"] = query_dict.urlencode()
    
    # --- КОНЕЦ СОРТИРОВКИ ---

    return render(request, "core/season_report.html", data)

@login_required
def update_rate_view(request):
    update_usd_rate()
    return redirect("/dashboard/")