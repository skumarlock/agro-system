import calendar

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from core.services.operations import get_user_operations
from django.core.paginator import Paginator
from core.services.currency import update_usd_rate
from core.services.utils import sort_resources
from core.services import (
    get_dashboard_data,
    get_field_crop_report,
    get_field_crops_reports,
    get_season_report,
    get_user_field_crop_or_404,
    get_user_season_or_404,
)
from core.models import Operation, Season
from core.forms import OperationForm, WorkerRegistrationForm
from django.http import HttpResponseForbidden
from core.forms import OperationForm
from core.models import OperationResource, Resource

def is_owner_or_admin(user):
    return user.role in ["owner", "admin"]

@login_required
def dashboard_view(request):
    if not is_owner_or_admin(request.user):
        return redirect("my-operations")
    period = request.GET.get("period", "all")

    month = request.GET.get("month")
    year = request.GET.get("year")
    season_id = request.GET.get("season_id")

    data = {
        "dashboard": get_dashboard_data(
            request.user,
            period=period,
            month=month,
            year=year,
            season_id=season_id,
    ),
    "user_role": request.user.role,
}

    if request.user.role == "owner":
        data["seasons"] = Season.objects.filter(
            field_crops__field__owner=request.user
        ).distinct()

    elif request.user.role == "worker":
        data["seasons"] = Season.objects.filter(
            field_crops__operations__performed_by=request.user
        ).distinct()

    else:
        data["seasons"] = Season.objects.all()

    data["seasons"] = data["seasons"].order_by("-start_date")
    from core.services.currency import get_usd_rate
    data["usd_rate"] = get_usd_rate()

    currency = request.GET.get("currency", "uzs")
    data["currency"] = currency

    sort = request.GET.get("sort")
    order = request.GET.get("order", "asc")

    resources = data["dashboard"]["resources"]

    resources, next_order = sort_resources(resources, sort, order)

    # выделение топ ресурса
    if resources:
        max_cost = max(r["cost"] for r in resources)
        for r in resources:
            r["is_top"] = r["cost"] == max_cost

    data["dashboard"]["resources"] = resources
    data["sort"] = sort
    data["order"] = order
    data["next_order"] = next_order
    data["is_worker"] = request.user.role == "worker"
    data["operations"] = get_user_operations(request.user)
    data["period"] = period
    data["is_owner"] = is_owner_or_admin(request.user)

    data["months"] = [
    (i, calendar.month_name[i])
    for i in range(1, 13)
]

    data["years"] = (
        Operation.objects
        .dates("date", "year")
        .values_list("date__year", flat=True)
    )
    
    query_dict = request.GET.copy()
    query_dict.pop("sort", None)
    query_dict.pop("order", None)
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

    # --- СОРТИРОВКА ---
    sort = request.GET.get("sort")
    order = request.GET.get("order", "asc")

    resources = data["report"]["resources"]

    resources, next_order = sort_resources(resources, sort, order)

    data["report"]["resources"] = resources
    data["sort"] = sort
    data["order"] = order
    data["next_order"] = next_order

    query_dict = request.GET.copy()
    query_dict.pop("sort", None)
    query_dict.pop("order", None)
    data["query_params"] = query_dict.urlencode()
    # --- КОНЕЦ ---

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

    resources, next_order = sort_resources(resources, sort, order)

    data["report"]["resources"] = resources
    data["sort"] = sort
    data["order"] = order
    data["next_order"] = next_order

    query_dict = request.GET.copy()
    query_dict.pop("sort", None)
    query_dict.pop("order", None)
    data["query_params"] = query_dict.urlencode()
    
    # --- КОНЕЦ СОРТИРОВКИ ---

    return render(request, "core/season_report.html", data)

@login_required
def update_rate_view(request):
    update_usd_rate()
    return redirect("/dashboard/")

@require_POST
@login_required
def toggle_operation_status(request, pk):
    op = get_object_or_404(Operation, pk=pk)

    # безопасность
    if request.user.role == "WORKER":
        if op.performed_by != request.user:
            return redirect("my-operations")

    # переключение
    if op.status == "done":
        op.status = "planned"
    else:
        op.status = "done"

    op.save()
    return redirect("my-operations")

@login_required
def my_operations_view(request):
    ops = get_user_operations(request.user)

    paginator = Paginator(ops, 10)  # 10 на страницу
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "core/my_operations.html", {
        "operations": page_obj,
        "page_obj": page_obj,
    })

@login_required
def create_operation(request):
    if request.user.role != "owner":
        return HttpResponseForbidden("You are not allowed to create operations")
    if request.method == "POST":
        form = OperationForm(request.POST, user=request.user)
        if form.is_valid():
            operation = form.save(commit=False)

            # защита
            if operation.performed_by.role != "worker":
                return HttpResponseForbidden("Invalid worker")
                if not operation.performed_by:
                    return HttpResponseForbidden("Worker not selected")

                if operation.performed_by.role != "worker":
                    return HttpResponseForbidden("Invalid worker")

            operation.save()

            resources = request.POST.getlist("resource")
            quantities = request.POST.getlist("quantity")

            for r_id, qty in zip(resources, quantities):
                if qty:
                    OperationResource.objects.create(
                        operation=operation,
                        resource_id=r_id,
                        quantity=qty
                    )

            return redirect("my-operations")
    else:
        form = OperationForm(user=request.user)

    return render(request, "core/create_operation.html", {
        "form": form,
        "resources": Resource.objects.all()
    })

@login_required
def home_redirect(request):
    if request.user.role == "worker":
        return redirect("my-operations")
    return redirect("dashboard")

@login_required
def create_worker(request):
    if request.user.role != "owner":
        return redirect("dashboard")

    if request.method == "POST":
        form = WorkerRegistrationForm(request.POST, owner=request.user)
        if form.is_valid():
            form.save()
            return redirect("field-crops")  # или dashboard
    else:
        form = WorkerRegistrationForm(owner=request.user)

    return render(request, "core/create_worker.html", {
        "form": form
    })