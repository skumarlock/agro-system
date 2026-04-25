import calendar
import json
from datetime import timedelta
from collections import Counter, defaultdict

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import now
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
from core.models import Operation, Season, User, AgronomistAssignment, FieldCrop, OperationResource, Field
from core.forms import OperationForm, WorkerRegistrationForm, InviteAgronomistForm
from django.http import HttpResponseForbidden, JsonResponse
from core.models import Resource

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

    # сортируем по убыванию стоимости
    resources = sorted(resources, key=lambda r: r.get("cost") or 0, reverse=True)

    top = resources[:6]
    other = resources[6:]

    if other:
        other_sum = sum((r.get("cost") or 0) for r in other)
        top.append({
            "name": "Other",
            "cost": other_sum,
            "type": "other"
        })

    resources, next_order = sort_resources(resources, sort, order)

    # выделение топ ресурса
    if resources:
        max_cost = max((r["cost"] or 0) for r in resources)
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

    if is_owner_or_admin(request.user):
        resources_by_type = defaultdict(float)
        usd_rate = float(data["usd_rate"] or 1)
        for resource in data["dashboard"]["resources"]:
            resource_type = resource.get("type") or "other"
            resources_by_type[resource_type] += float(resource.get("cost") or 0)

        operations_qs = Operation.objects.filter(field_crop__field__owner=request.user)

        if period == "month":
            if month and year:
                operations_qs = operations_qs.filter(date__month=month, date__year=year)
            else:
                today = now().date()
                operations_qs = operations_qs.filter(date__month=today.month, date__year=today.year)
        elif period == "season":
            if season_id:
                operations_qs = operations_qs.filter(field_crop__season_id=season_id)
            else:
                today = now().date()
                operations_qs = operations_qs.filter(
                    field_crop__season__start_date__lte=today,
                    field_crop__season__end_date__gte=today,
                )

        dates_list = list(operations_qs.order_by("date").values_list("date", flat=True))

        if dates_list:
            delta_days = (dates_list[-1] - dates_list[0]).days
            if delta_days > 365:
                grouped = [d.replace(day=1) for d in dates_list]
                fmt = "%Y-%m"
            elif delta_days >= 90:
                grouped = [d - timedelta(days=d.weekday()) for d in dates_list]
                fmt = "%Y-%m-%d"
            else:
                grouped = dates_list
                fmt = "%Y-%m-%d"
            ops_over_time = [
                {"date": d.strftime(fmt), "count": c}
                for d, c in sorted(Counter(grouped).items())
            ]
        else:
            ops_over_time = []

        data["charts"] = {
            "cost_by_resource": [
                {
                    "name": resource["name"],
                    "cost_local": float(resource.get("cost") or 0),
                    "cost_usd": float(resource.get("cost") or 0) / usd_rate if usd_rate else 0,
                }
                for resource in top
            ],
            "cost_by_resource_type": [
                {
                    "type": resource_type.replace("_", " ").title(),
                    "cost_local": cost,
                    "cost_usd": cost / usd_rate if usd_rate else 0,
                }
                for resource_type, cost in resources_by_type.items()
            ],
            "operations_over_time": ops_over_time,
        }

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
    include_finances = request.user.role != "agronomist"

    data = {
        "report": get_field_crop_report(field_crop, include_finances=include_finances),
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

@login_required
@require_POST
def toggle_operation_status(request, pk):
    op = get_object_or_404(Operation, pk=pk)

    if request.user.role == "worker":
        if op.performed_by != request.user:
            return redirect("my-operations")

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
    if request.user.role not in ["owner", "agronomist"]:
        return HttpResponseForbidden("You are not allowed to create operations")

    if request.method == "POST":
        form = OperationForm(request.POST, user=request.user)

        if form.is_valid():
            base_op = form.save(commit=False)

            resources = request.POST.getlist("resource")
            quantities = request.POST.getlist("quantity")

            resource_map = {}
            for r_id, qty in zip(resources, quantities):
                if not qty:
                    continue
                qty = float(qty)
                resource_map[r_id] = resource_map.get(r_id, 0) + qty

            if not resource_map:
                return HttpResponseForbidden("At least one resource required")

            if not base_op.performed_by:
                return HttpResponseForbidden("Worker not selected")

            if base_op.performed_by.role != "worker":
                return HttpResponseForbidden("Invalid worker")

            # Build schedule: JSON list wins over single date
            schedule_json = request.POST.get("schedule")
            if schedule_json:
                try:
                    schedule = json.loads(schedule_json)
                except (ValueError, TypeError):
                    schedule = [{"date": form.cleaned_data["date"].isoformat()}]
            else:
                schedule = [{"date": form.cleaned_data["date"].isoformat()}]

            today = now().date()
            for item in schedule:
                from datetime import date as date_cls
                item_date = date_cls.fromisoformat(item["date"])
                # Auto-status: past dates → done
                op_status = base_op.status
                if op_status == "planned" and item_date < today:
                    op_status = "done"

                op = Operation.objects.create(
                    field_crop=base_op.field_crop,
                    type=base_op.type,
                    date=item_date,
                    status=op_status,
                    performed_by=base_op.performed_by,
                    description=base_op.description,
                )
                # Clone resources to every operation
                for r_id, qty in resource_map.items():
                    OperationResource.objects.create(
                        operation=op,
                        resource_id=r_id,
                        quantity=qty,
                    )

            def get_redirect_for_user(user):
                if user.role == "owner":
                    return "dashboard"
                elif user.role == "worker":
                    return "my-operations"
                elif user.role == "agronomist":
                    return "agronomist-dashboard"
                return "dashboard"

            next_url = request.POST.get("next") or request.GET.get("next")
            if next_url:
                return redirect(next_url)
            return redirect(get_redirect_for_user(request.user))

    else:
        form = OperationForm(user=request.user)

    # Cascade data for Field → Season → FieldCrop
    if request.user.role == "agronomist":
        owner_ids = AgronomistAssignment.objects.filter(
            agronomist=request.user
        ).values_list("owner_id", flat=True)
        fields_qs = Field.objects.filter(owner_id__in=owner_ids)
        fc_qs = FieldCrop.objects.filter(field__owner_id__in=owner_ids).select_related("field", "season", "crop")
    else:
        fields_qs = Field.objects.filter(owner=request.user)
        fc_qs = FieldCrop.objects.filter(field__owner=request.user).select_related("field", "season", "crop")

    seasons_qs = Season.objects.all()

    fields_data = [{"id": f.id, "name": f.name} for f in fields_qs]
    field_crops_data = [
        {"id": fc.id, "field_id": fc.field_id, "season_id": fc.season_id, "name": fc.crop.name}
        for fc in fc_qs
    ]
    seasons_data = [
        {
            "id": s.id,
            "name": str(s),
            "start_date": s.start_date.isoformat(),
            "end_date": s.end_date.isoformat(),
        }
        for s in seasons_qs
    ]

    return render(request, "core/create_operation.html", {
        "form": form,
        "resources": Resource.objects.all(),
        "fields": fields_data,
        "field_crops": field_crops_data,
        "seasons": seasons_data,
    })

@login_required
def home_redirect(request):
    if request.user.role == "worker":
        return redirect("my-operations")

    if request.user.role == "agronomist":
        return redirect("agronomist-dashboard")

    return redirect("dashboard")

@login_required
def create_worker(request):
    if request.user.role != "owner":
        return HttpResponseForbidden("Access denied")

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

@login_required
def invite_agronomist(request):
    if request.user.role != "owner":
        return HttpResponseForbidden("Access denied")

    if request.method == "POST":
        form = InviteAgronomistForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]

            try:
                agronomist = User.objects.get(email=email)
            except User.DoesNotExist:
                messages.error(request, "No agronomist found with this email")
                return redirect("invite-agronomist")

            if agronomist.role != "agronomist":
                messages.error(request, "This user is not an agronomist")
                return redirect("invite-agronomist")

            AgronomistAssignment.objects.get_or_create(
                owner=request.user,
                agronomist=agronomist
            )

            messages.success(request, "Agronomist connected")
            return redirect("field-crops")
    else:
        form = InviteAgronomistForm()

    return render(request, "core/invite_agronomist.html", {"form": form})

@login_required
def my_agronomists(request):
    if request.user.role != "owner":
        return HttpResponseForbidden("Access denied")

    links = AgronomistAssignment.objects.filter(owner=request.user)

    return render(request, "core/my_agronomists.html", {
        "links": links
    })

@login_required
@require_POST
def remove_agronomist(request, pk):
    if request.user.role != "owner":
        return HttpResponseForbidden("Access denied")

    link = get_object_or_404(
        AgronomistAssignment,
        pk=pk,
        owner=request.user
    )
    link.delete()

    return JsonResponse({
    "success": True
})

@login_required
def agronomist_dashboard(request):
    if request.user.role != "agronomist":
        return redirect("dashboard")



    links = AgronomistAssignment.objects.filter(agronomist=request.user)

    return render(request, "core/agronomist_dashboard.html", {
        "links": links
    })

@login_required
def agronomist_owner_detail(request, owner_id):
    if request.user.role != "agronomist":
        return redirect("dashboard")

    link = AgronomistAssignment.objects.filter(
        owner_id=owner_id,
        agronomist=request.user
    ).first()

    if not link:
        return redirect("agronomist-dashboard")

    can_view_finances = link.can_view_finances

    field_crops = FieldCrop.objects.filter(field__owner_id=owner_id)\
        .select_related("field", "crop", "season")

    reports = [
        get_field_crop_report(fc, include_finances=can_view_finances)
        for fc in field_crops
    ]

    return render(request, "core/agronomist_owner_detail.html", {
        "reports": reports
    })


@login_required
def agronomist_field_operations(request, pk):
    if request.user.role != "agronomist":
        return redirect("dashboard")

    field_crop = get_object_or_404(
        FieldCrop.objects.select_related("field", "crop", "season"),
        pk=pk,
    )

    link = AgronomistAssignment.objects.filter(
        owner=field_crop.field.owner,
        agronomist=request.user,
    ).first()

    if not link:
        return redirect("agronomist-dashboard")

    operations = Operation.objects.filter(
        field_crop=field_crop
    ).select_related("field_crop", "performed_by")

    return render(request, "core/agronomist_operations.html", {
        "field_crop": field_crop,
        "operations": operations,
    })

@login_required
@require_POST
def toggle_finance_access(request, pk):
    if request.user.role != "owner":
        return JsonResponse({"success": False}, status=403)

    link = get_object_or_404(
        AgronomistAssignment,
        pk=pk,
        owner=request.user
    )

    link.can_view_finances = not link.can_view_finances
    link.save()

    return JsonResponse({
        "success": True,
        "can_view_finances": link.can_view_finances
    })
