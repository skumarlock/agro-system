import calendar
import json
from datetime import timedelta
from collections import Counter, defaultdict

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.timezone import now
from django.db import IntegrityError
from django.core.exceptions import ValidationError
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
from core.forms import OperationForm, WorkerRegistrationForm, InviteAgronomistForm, SeasonCreateForm
from django.http import HttpResponseForbidden, JsonResponse
from django.urls import reverse
from core.models import Resource


def get_home_url(user):
    """Return the correct home URL name for each role."""
    if user.role == "worker":
        return "my-operations"
    if user.role == "agronomist":
        return "agronomist-dashboard"
    return "dashboard"


def is_owner_or_admin(user):
    return user.role in ["owner", "admin"]


def get_operation_for_user_or_403(user, pk):
    qs = Operation.objects.select_related(
        "field_crop__field",
        "field_crop__crop",
        "performed_by",
    ).prefetch_related("operation_resources__resource")

    if user.role == "worker":
        qs = qs.filter(performed_by=user)
    elif user.role == "agronomist":
        qs = qs.filter(field_crop__field__owner__agronomist_links__agronomist=user)
    elif user.role not in ["owner", "admin"]:
        return None
    else:
        qs = qs.filter(field_crop__field__owner=user)

    return qs.distinct().filter(pk=pk).first()

@login_required
def dashboard_view(request):
    if not is_owner_or_admin(request.user):
        return redirect(get_home_url(request.user))

    # Block A: date-range + quick period filters (no more season dropdown)
    period     = request.GET.get("period", "all")   # all | month | year
    month      = request.GET.get("month")
    year       = request.GET.get("year")
    from_date  = request.GET.get("from_date") or None
    to_date    = request.GET.get("to_date") or None

    # Parse date-range strings to date objects
    from datetime import date as date_cls
    def _parse_date(s):
        try:
            return date_cls.fromisoformat(s)
        except Exception:
            return None

    from_date_obj = _parse_date(from_date) if from_date else None
    to_date_obj   = _parse_date(to_date)   if to_date   else None

    # If custom range provided, override period
    if from_date_obj and to_date_obj:
        period = "range"

    data = {
        "dashboard": get_dashboard_data(
            request.user,
            period=period,
            month=month,
            year=year,
            from_date=from_date_obj,
            to_date=to_date_obj,
        ),
        "user_role": request.user.role,
    }

    from core.services.currency import get_usd_rate
    data["usd_rate"] = get_usd_rate()
    currency = request.GET.get("currency", "uzs")
    data["currency"] = currency

    sort  = request.GET.get("sort")
    order = request.GET.get("order", "asc")

    resources = data["dashboard"]["resources"]
    resources = sorted(resources, key=lambda r: r.get("cost") or 0, reverse=True)

    top   = resources[:6]
    other = resources[6:]
    if other:
        other_sum = sum((r.get("cost") or 0) for r in other)
        top.append({"name": "Other", "cost": other_sum, "type": "other"})

    resources, next_order = sort_resources(resources, sort, order)
    if resources:
        max_cost = max((r["cost"] or 0) for r in resources)
        for r in resources:
            r["is_top"] = r["cost"] == max_cost

    data["dashboard"]["resources"] = resources
    data["sort"]        = sort
    data["order"]       = order
    data["next_order"]  = next_order
    data["is_worker"]   = request.user.role == "worker"
    data["operations"]  = get_user_operations(request.user)
    data["period"]      = period
    data["is_owner"]    = is_owner_or_admin(request.user)
    data["from_date"]   = from_date or ""
    data["to_date"]     = to_date or ""
    data["month"]       = month or ""
    data["year"]        = year or ""

    data["years"] = (
        Operation.objects
        .filter(field_crop__field__owner=request.user)
        .dates("date", "year")
        .values_list("date__year", flat=True)
    )

    query_dict = request.GET.copy()
    query_dict.pop("sort", None)
    query_dict.pop("order", None)
    query_dict.pop("currency", None)
    data["query_params"] = query_dict.urlencode()

    if is_owner_or_admin(request.user):
        resources_by_type = defaultdict(float)
        usd_rate = float(data["usd_rate"] or 1)
        for resource in data["dashboard"]["resources"]:
            resource_type = resource.get("type") or "other"
            resources_by_type[resource_type] += float(resource.get("cost") or 0)

        # Operations over time scoped to same period
        operations_qs = Operation.objects.filter(field_crop__field__owner=request.user)
        if from_date_obj and to_date_obj:
            operations_qs = operations_qs.filter(date__gte=from_date_obj, date__lte=to_date_obj)
        elif period == "month":
            if month and year:
                operations_qs = operations_qs.filter(date__month=month, date__year=year)
            else:
                today = now().date()
                operations_qs = operations_qs.filter(date__month=today.month, date__year=today.year)
        elif period == "year":
            y = int(year) if year else now().date().year
            operations_qs = operations_qs.filter(date__year=y)

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
    reports = get_field_crops_reports(request.user)
    # Attach computed status to each report
    # get_field_crops_reports returns dicts; we attach computed status separately
    fc_ids = [r["field_crop_id"] for r in reports]
    fc_map = {fc.id: fc for fc in FieldCrop.objects.prefetch_related("operations").filter(id__in=fc_ids)}
    for r in reports:
        fc = fc_map.get(r["field_crop_id"])
        r["computed_status"] = fc.get_computed_status() if fc else r.get("status", "planned")

    # Seasons for filter (owner-scoped)
    if request.user.role == "agronomist":
        owner_ids = AgronomistAssignment.objects.filter(
            agronomist=request.user
        ).values_list("owner_id", flat=True)
        seasons = Season.objects.filter(owner_id__in=owner_ids).order_by("-year")
    else:
        seasons = Season.objects.filter(owner=request.user).order_by("-year")

    return render(request, "core/field_crop_list.html", {
        "field_crops": reports,
        "seasons": seasons,
        "is_owner": request.user.role == "owner",
    })


@login_required
def field_crop_detail_view(request, pk):
    field_crop = get_user_field_crop_or_404(request.user, pk)

    # Finance visibility: owners always see it; agronomists only if can_view_finances=True
    if request.user.role == "agronomist":
        link = AgronomistAssignment.objects.filter(
            agronomist=request.user,
            owner=field_crop.field.owner,
        ).first()
        include_finances = bool(link and link.can_view_finances)
    else:
        include_finances = True

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

    if request.user.role == "agronomist":
        link = AgronomistAssignment.objects.filter(
            agronomist=request.user,
            owner=season.owner,
        ).first()
        include_finances = bool(link and link.can_view_finances)
    else:
        include_finances = True

    data = {
        "report": get_season_report(season, request.user, include_finances=include_finances),
        "can_view_finances": include_finances,
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
    op = get_operation_for_user_or_403(request.user, pk)
    if not op:
        return HttpResponseForbidden("You are not allowed to update this operation")

    if op.status == "done":
        op.status = "planned"
    else:
        op.status = "done"

    op.save()

    # Preserve pagination and filter state
    page   = request.POST.get("page", "1")
    filt   = request.POST.get("filter", "all")
    sort   = request.POST.get("sort", "-date")
    year   = request.POST.get("year", "")
    next_url = request.POST.get("next")
    if next_url:
        joiner = "&" if "?" in next_url else "?"
        return redirect(f"{next_url}{joiner}op={op.pk}#op-{op.pk}")

    url = reverse("my-operations")
    return redirect(f"{url}?page={page}&filter={filt}&sort={sort}&year={year}#op-{op.pk}")


@login_required
def edit_operation(request, pk):
    if request.user.role not in ["owner", "agronomist"]:
        return HttpResponseForbidden("You are not allowed to edit operations")

    op = get_operation_for_user_or_403(request.user, pk)
    if not op:
        return HttpResponseForbidden("You are not allowed to edit this operation")

    next_url = request.GET.get("next") or request.POST.get("next") or reverse("field-detail", args=[op.field_crop.field_id])

    if request.method == "POST":
        form = OperationForm(request.POST, instance=op, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Operation updated.")
            return redirect(f"{next_url}#op-{op.pk}")
    else:
        form = OperationForm(instance=op, user=request.user)

    return render(request, "core/edit_operation.html", {
        "form": form,
        "operation": op,
        "next": next_url,
    })


@login_required
@require_POST
def delete_operation(request, pk):
    if request.user.role not in ["owner", "agronomist"]:
        return HttpResponseForbidden("You are not allowed to delete operations")

    op = get_operation_for_user_or_403(request.user, pk)
    if not op:
        return HttpResponseForbidden("You are not allowed to delete this operation")

    next_url = request.POST.get("next") or reverse("field-detail", args=[op.field_crop.field_id])
    op.delete()
    messages.success(request, "Operation deleted.")
    return redirect(next_url)

@login_required
def my_operations_view(request):
    filter_param = request.GET.get("filter", "all")
    sort_param   = request.GET.get("sort", "-date")
    year_param   = request.GET.get("year", "")   # Block G: year filter

    ops = get_user_operations(request.user)

    today = now().date()
    if filter_param == "today":
        ops = ops.filter(date=today)
    elif filter_param == "week":
        ops = ops.filter(date__gte=today - timedelta(days=7))

    # Block G: year filter
    if year_param:
        try:
            ops = ops.filter(date__year=int(year_param))
        except ValueError:
            pass

    allowed_sorts = {"date", "-date", "status", "-status"}
    if sort_param not in allowed_sorts:
        sort_param = "-date"
    ops = ops.order_by(sort_param)

    paginator = Paginator(ops, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Block G: available years for this worker
    available_years = list(
        get_user_operations(request.user)
        .dates("date", "year")
        .values_list("date__year", flat=True)
    )

    return render(request, "core/my_operations.html", {
        "operations": page_obj,
        "page_obj": page_obj,
        "filter": filter_param,
        "sort": sort_param,
        "year": year_param,
        "available_years": available_years,
    })

@login_required
def create_operation(request):
    if request.user.role not in ["owner", "agronomist"]:
        return HttpResponseForbidden("You are not allowed to create operations")

    if request.method == "POST":
        schedule_json = request.POST.get("schedule")
        form = OperationForm(
            request.POST,
            user=request.user,
            schedule_mode=bool(schedule_json),
        )

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

            # Handle per-resource price overrides (Block A)
            if request.user.role == "owner":
                from core.models import ResourcePrice
                for r_id_str in resource_map:
                    price_str = request.POST.get(f"price_{r_id_str}")
                    if price_str:
                        try:
                            new_price = float(price_str)
                            if new_price > 0:
                                ResourcePrice.objects.update_or_create(
                                    owner=request.user,
                                    resource_id=int(r_id_str),
                                    defaults={"price": new_price},
                                )
                        except (ValueError, TypeError):
                            pass

            # Build schedule from POST JSON or single form date
            schedule_json = request.POST.get("schedule")
            if schedule_json:
                try:
                    schedule = json.loads(schedule_json)
                except (ValueError, TypeError):
                    schedule = [{"date": form.cleaned_data["date"].isoformat()}]
            else:
                schedule = [{"date": form.cleaned_data["date"].isoformat()}]

            today = now().date()
            from datetime import date as date_cls
            for item in schedule:
                item_date = date_cls.fromisoformat(item["date"])
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

                # Support per-date resource overrides from preview flow
                if "resources" in item and item["resources"]:
                    for r in item["resources"]:
                        OperationResource.objects.create(
                            operation=op,
                            resource_id=r["id"],
                            quantity=r["quantity"],
                        )
                else:
                    # Clone base resources to every operation
                    for r_id, qty in resource_map.items():
                        OperationResource.objects.create(
                            operation=op,
                            resource_id=r_id,
                            quantity=qty,
                        )

            next_url = request.POST.get("next") or request.GET.get("next")
            if next_url:
                return redirect(next_url)
            return redirect(get_home_url(request.user))

        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("create_operation form invalid: %s", form.errors)

    else:
        form = OperationForm(user=request.user)

    # Cascade data for Field → Season → FieldCrop
    if request.user.role == "agronomist":
        owner_ids = AgronomistAssignment.objects.filter(
            agronomist=request.user
        ).values_list("owner_id", flat=True)
        fields_qs = Field.objects.filter(owner_id__in=owner_ids).select_related("owner")
        fc_qs = FieldCrop.objects.filter(field__owner_id__in=owner_ids).select_related("field", "season", "crop")
        seasons_qs = Season.objects.filter(owner_id__in=owner_ids)
    else:
        fields_qs = Field.objects.filter(owner=request.user).select_related("owner")
        fc_qs = FieldCrop.objects.filter(field__owner=request.user).select_related("field", "season", "crop")
        seasons_qs = Season.objects.filter(owner=request.user)

    fields_data = [{"id": f.id, "name": f.name, "owner_id": f.owner_id} for f in fields_qs]
    field_crops_data = [
        {"id": fc.id, "field_id": fc.field_id, "season_id": fc.season_id, "name": fc.crop.name}
        for fc in fc_qs
    ]
    seasons_data = [
        {
            "id": s.id,
            "name": str(s),
            "owner_id": s.owner_id,
            "start_date": s.start_date.isoformat(),
            "end_date": s.end_date.isoformat(),
        }
        for s in seasons_qs.order_by("-start_date")
    ]

    return render(request, "core/create_operation.html", {
        "form": form,
        "resources": Resource.objects.all(),
        "fields": fields_data,
        "field_crops": field_crops_data,
        "seasons": seasons_data,
        "preselect_field_id": request.GET.get("field_id", ""),
        "preselect_season_id": request.GET.get("season_id", ""),
        "next": request.GET.get("next", ""),
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

    year_param = request.GET.get("year", "")
    fields = Field.objects.filter(owner_id=owner_id).distinct().order_by("name")

    if year_param:
        try:
            fields = fields.filter(field_crops__season__year=int(year_param)).distinct()
        except ValueError:
            year_param = ""

    available_years = list(
        Season.objects.filter(owner_id=owner_id)
        .order_by("-year")
        .values_list("year", flat=True)
        .distinct()
    )

    return render(request, "core/agronomist_owner_detail.html", {
        "fields": fields,
        "owner": link.owner,
        "year": year_param,
        "available_years": available_years,
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
    ).select_related("field_crop__crop", "performed_by").prefetch_related("operation_resources__resource")

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


@login_required
def create_season(request):
    if request.user.role != "owner":
        return HttpResponseForbidden("Only owners can create seasons")

    next_url = request.GET.get("next") or request.POST.get("next") or "fields-list"

    if request.method == "POST":
        form = SeasonCreateForm(request.POST)
        if form.is_valid():
            season = form.save(commit=False)
            season.owner = request.user
            if Season.objects.filter(
                owner=request.user,
                name=season.name,
                year=season.start_date.year,
            ).exists():
                messages.error(request, "Season already exists")
                return redirect(request.path)

            try:
                season.save()
            except (IntegrityError, ValidationError) as exc:
                message = "Season already exists" if isinstance(exc, IntegrityError) else "; ".join(exc.messages)
                messages.error(request, message)
                return redirect(request.path)

            messages.success(request, f"Season '{season}' created successfully.")
            return redirect(next_url)
    else:
        form = SeasonCreateForm()

    return render(request, "core/create_season.html", {
        "form": form,
        "next": next_url,
    })


# ─────────────────────────────────────────────
# FIELDS — entry point
# ─────────────────────────────────────────────

@login_required
def field_list_view(request):
    """Fields-first entry point for owners and agronomists."""
    today = now().date()

    if request.user.role == "agronomist":
        owner_ids = AgronomistAssignment.objects.filter(
            agronomist=request.user
        ).values_list("owner_id", flat=True)
        fields_qs = Field.objects.filter(owner_id__in=owner_ids).select_related("owner")
    else:
        fields_qs = Field.objects.filter(owner=request.user)

    # Annotate each field with its active season and crop count
    field_data = []
    for f in fields_qs:
        seasons = Season.objects.filter(owner=f.owner).order_by("-start_date")

        active_season = seasons.filter(
            start_date__lte=today,
            end_date__gte=today
        ).first()

        field_crops = FieldCrop.objects.filter(field=f).prefetch_related("operations")
        total_crop_count = field_crops.count()
        active_crop_count = sum(
            1 for fc in field_crops
            if fc.get_computed_status() == "active"
        )

        field_data.append({
            "field": f,
            "active_season": active_season,
            "active_crop_count": active_crop_count,
            "total_crop_count": total_crop_count,
            "seasons_count": seasons.count(),
        })

    return render(request, "core/field_list.html", {
        "field_data": field_data,
        "is_owner": request.user.role == "owner",
    })


@login_required
def field_detail_view(request, pk):
    """Field detail page: seasons tabs + FieldCrop list + operations table."""
    today = now().date()

    # Block E: Access check with distinct()
    if request.user.role == "agronomist":
        owner_ids = AgronomistAssignment.objects.filter(
            agronomist=request.user
        ).values_list("owner_id", flat=True)
        field = get_object_or_404(Field, pk=pk, owner_id__in=owner_ids)
    else:
        field = get_object_or_404(Field, pk=pk, owner=request.user)

    all_seasons = Season.objects.filter(owner=field.owner).order_by("-start_date")

    active_seasons = [s for s in all_seasons if s.start_date <= today <= s.end_date]
    past_seasons   = [s for s in all_seasons if s.end_date < today]
    future_seasons = [s for s in all_seasons if s.start_date > today]

    selected_season_id = request.GET.get("season")
    if selected_season_id:
        selected_season = next((s for s in all_seasons if str(s.id) == selected_season_id), None)
    else:
        selected_season = active_seasons[0] if active_seasons else (all_seasons.first() if all_seasons.exists() else None)

    # Block C/D: Field crops + per-season operations with resources prefetched
    field_crops = []
    operations_for_season = []
    if selected_season:
        fcs = FieldCrop.objects.filter(
            field=field, season=selected_season
        ).prefetch_related(
            "operations__operation_resources__resource",  # Block D
            "operations__performed_by",
        ).select_related("crop")

        for fc in fcs:
            ops_qs = list(fc.operations.all())
            field_crops.append({
                "fc": fc,
                "computed_status": fc.get_computed_status(),
                "ops_total": len(ops_qs),
                "ops_done": sum(1 for o in ops_qs if o.status == "done"),
            })
            operations_for_season.extend(ops_qs)

        # Sort operations by date descending
        operations_for_season.sort(key=lambda o: o.date, reverse=True)

    return render(request, "core/field_detail.html", {
        "field": field,
        "active_seasons": active_seasons,
        "past_seasons": past_seasons,
        "future_seasons": future_seasons,
        "selected_season": selected_season,
        "field_crops": field_crops,
        "operations": operations_for_season,
        "is_owner": request.user.role == "owner",
    })
