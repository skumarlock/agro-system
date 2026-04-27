import calendar
import json
import logging
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
from core.models import Operation, Season, User, AgronomistAssignment, FieldCrop, OperationResource, Field, OperationType
from core.forms import (
    FieldCropCreateForm,
    InviteAgronomistForm,
    OperationForm,
    SeasonCreateForm,
    WorkerRegistrationForm,
)
from django.http import HttpResponseForbidden, JsonResponse
from django.urls import reverse
from core.models import Resource

logger = logging.getLogger(__name__)


def get_home_url(user):
    """Return the correct home URL name for each role."""
    if user.role == "worker":
        return "my-operations"
    if user.role == "agronomist":
        return "agronomist-dashboard"
    return "dashboard"


def is_owner_or_admin(user):
    return user.role in ["owner", "admin"]


def get_active_owner_for_user(user, request=None):
    if user.role == "owner":
        return user
    if user.role == "agronomist":
        owner_id = request.session.get("active_owner_id") if request else None
        qs = User.objects.filter(
            role="owner",
            agronomist_links__agronomist=user,
        )
        if owner_id:
            owner = qs.filter(pk=owner_id).first()
            if owner:
                return owner
        return qs.first()
    return user.owner


def get_operation_for_user_or_403(user, pk):
    qs = Operation.objects.select_related(
        "field_crop__field",
        "field_crop__crop",
        "type",
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


def get_agronomist_assignment_for_owner(user, owner):
    if user.role != "agronomist":
        return None
    return AgronomistAssignment.objects.filter(
        agronomist=user,
        owner=owner,
    ).first()


def can_manage_operations_for_owner(user, owner):
    if user.role in ["owner", "admin"]:
        return True
    link = get_agronomist_assignment_for_owner(user, owner)
    return bool(link and link.can_manage_operations)


def can_manage_seasons_for_owner(user, owner):
    if user.role in ["owner", "admin"]:
        return True
    link = get_agronomist_assignment_for_owner(user, owner)
    return bool(link and link.can_manage_seasons)


def can_manage_field_crops_for_owner(user, owner):
    if user.role in ["owner", "admin"]:
        return True
    link = get_agronomist_assignment_for_owner(user, owner)
    return bool(link and link.can_manage_field_crops)


def _get_manageable_season_or_404(request, pk):
    qs = Season.objects.all()
    if request.user.role == "owner":
        qs = qs.filter(owner=request.user)
    elif request.user.role != "admin":
        return None
    return qs.filter(pk=pk).first()


def _get_manageable_field_crop_or_404(request, pk):
    qs = FieldCrop.objects.select_related("field", "season", "crop")
    if request.user.role == "owner":
        qs = qs.filter(field__owner=request.user)
    elif request.user.role != "admin":
        return None
    return qs.filter(pk=pk).first()


def _get_field_crop_form_context(request, form, *, next_url="", preselect_field_id="", preselect_season_id="", form_title="Добавить культуру", submit_label="Добавить культуру"):
    if request.user.role == "owner":
        fields_qs = Field.objects.filter(owner=request.user).select_related("owner")
        seasons_qs = Season.objects.filter(owner=request.user)
    else:
        fields_qs = Field.objects.select_related("owner").all()
        seasons_qs = Season.objects.all()

    return {
        "form": form,
        "next": next_url,
        "preselect_field_id": preselect_field_id,
        "preselect_season_id": preselect_season_id,
        "season_years": sorted({s.year for s in seasons_qs}, reverse=True),
        "seasons_data": [
            {
                "id": s.id,
                "name": str(s),
                "year": s.year,
                "owner_id": s.owner_id,
            }
            for s in seasons_qs.order_by("-start_date")
        ],
        "fields_data": [
            {
                "id": f.id,
                "name": f.name,
                "owner_id": f.owner_id,
            }
            for f in fields_qs.order_by("name")
        ],
        "form_title": form_title,
        "submit_label": submit_label,
    }


def _get_create_operation_context(request, form):
    if request.user.role == "agronomist":
        active_owner = get_active_owner_for_user(request.user, request)
        owner_ids = [active_owner.id] if active_owner else list(
            AgronomistAssignment.objects.filter(
                agronomist=request.user
            ).values_list("owner_id", flat=True)
        )
        fields_qs = Field.objects.filter(owner_id__in=owner_ids).select_related("owner")
        fc_qs = FieldCrop.objects.filter(field__owner_id__in=owner_ids).select_related("field", "season", "crop")
        seasons_qs = Season.objects.filter(owner_id__in=owner_ids)
    else:
        fields_qs = Field.objects.filter(owner=request.user).select_related("owner")
        fc_qs = FieldCrop.objects.filter(field__owner=request.user).select_related("field", "season", "crop")
        seasons_qs = Season.objects.filter(owner=request.user)

    fields_data = [{"id": f.id, "name": f.name, "owner_id": f.owner_id} for f in fields_qs]
    field_crops_data = [
        {
            "id": fc.id,
            "field_id": fc.field_id,
            "crop_id": fc.crop_id,
            "season_id": fc.season_id,
            "season_year": fc.season.year,
            "name": fc.crop.name,
        }
        for fc in fc_qs
    ]
    season_years = sorted({s.year for s in seasons_qs}, reverse=True)
    seasons_data = [
        {
            "id": s.id,
            "name": str(s),
            "owner_id": s.owner_id,
            "start_date": s.start_date.isoformat(),
            "end_date": s.end_date.isoformat(),
            "year": s.year,
        }
        for s in seasons_qs.order_by("-start_date")
    ]

    return {
        "form": form,
        "resources": Resource.objects.all(),
        "fields": fields_data,
        "field_crops": field_crops_data,
        "seasons": seasons_data,
        "season_years": season_years,
        "preselect_field_id": request.POST.get("field") or request.GET.get("field_id", ""),
        "preselect_season_id": request.POST.get("season") or request.GET.get("season_id", ""),
        "next": request.POST.get("next") or request.GET.get("next", ""),
    }


def _resolve_field_crop_for_operation(request, field_id, crop_id, season_id):
    selected_season = Season.objects.filter(pk=season_id).first()
    if not selected_season:
        raise FieldCrop.DoesNotExist

    field_crop_qs = FieldCrop.objects.select_related("field", "season", "crop")
    if request.user.role == "agronomist":
        owner_ids = AgronomistAssignment.objects.filter(
            agronomist=request.user
        ).values_list("owner_id", flat=True)
        field_crop_qs = field_crop_qs.filter(field__owner_id__in=owner_ids)
        active_owner = get_active_owner_for_user(request.user, request)
        if active_owner:
            field_crop_qs = field_crop_qs.filter(field__owner=active_owner)
    else:
        field_crop_qs = field_crop_qs.filter(field__owner=request.user)

    logger.info(
        "create_operation FieldCrop candidates user_id=%s season_id=%s season_year=%s ids=%s",
        request.user.id,
        season_id,
        selected_season.year,
        list(field_crop_qs.values_list("id", flat=True)[:20]),
    )

    exact_fc = field_crop_qs.filter(
        field_id=field_id,
        crop_id=crop_id,
        season_id=season_id,
    ).first()
    if exact_fc:
        return exact_fc

    year_fc = field_crop_qs.filter(
        field_id=field_id,
        crop_id=crop_id,
        season__year=selected_season.year,
    ).order_by("season__start_date", "id").first()
    if year_fc:
        return year_fc

    raise FieldCrop.DoesNotExist


def _is_harvest_operation(operation_type):
    type_name = (operation_type.name or "").strip().lower()
    return type_name in {"сбор урожая", "harvesting", "harvest"}

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
        "status_active": FieldCrop.Status.ACTIVE,
        "status_harvested": FieldCrop.Status.HARVESTED,
    })


@login_required
def field_crop_detail_view(request, pk):
    field_crop = get_user_field_crop_or_404(request.user, pk)
    can_manage_field_crops = can_manage_field_crops_for_owner(request.user, field_crop.field.owner)

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
        "can_manage_field_crops": can_manage_field_crops,
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
    data["status_active"] = FieldCrop.Status.ACTIVE
    data["status_harvested"] = FieldCrop.Status.HARVESTED

    query_dict = request.GET.copy()
    query_dict.pop("sort", None)
    query_dict.pop("order", None)
    data["query_params"] = query_dict.urlencode()
    # --- КОНЕЦ ---

    return render(request, "core/field_crop_detail.html", data) 


@login_required
def season_report_view(request, pk):
    season = get_user_season_or_404(request.user, pk)
    can_manage_seasons = can_manage_seasons_for_owner(request.user, season.owner)

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
        "can_manage_seasons": can_manage_seasons,
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
    if not can_manage_operations_for_owner(request.user, op.field_crop.field.owner):
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
    if request.user.role not in ["owner", "agronomist", "admin"]:
        return HttpResponseForbidden("You are not allowed to edit operations")

    op = get_operation_for_user_or_403(request.user, pk)
    if not op:
        return HttpResponseForbidden("You are not allowed to edit this operation")
    if not can_manage_operations_for_owner(request.user, op.field_crop.field.owner):
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
    if request.user.role not in ["owner", "agronomist", "admin"]:
        return HttpResponseForbidden("You are not allowed to delete operations")

    op = get_operation_for_user_or_403(request.user, pk)
    if not op:
        return HttpResponseForbidden("You are not allowed to delete this operation")
    if not can_manage_operations_for_owner(request.user, op.field_crop.field.owner):
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
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        ops = ops.filter(date__gte=week_start, date__lte=week_end)

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

    owner = get_active_owner_for_user(request.user, request)
    if request.user.role == "agronomist" and (not owner or not can_manage_operations_for_owner(request.user, owner)):
        return HttpResponseForbidden("You are not allowed to create operations")

    if request.method == "POST":
        post_data = request.POST.copy()
        custom_type_name = post_data.get("new_operation_type", "").strip()
        if custom_type_name:
            op_type, _ = OperationType.objects.get_or_create(
                owner=owner,
                name=custom_type_name,
            )
            post_data["type"] = str(op_type.pk)

        schedule_json = request.POST.get("schedule")
        form = OperationForm(
            post_data,
            user=request.user,
            schedule_mode=bool(schedule_json),
        )

        if form.is_valid():
            base_op = form.save(commit=False)
            field_id = request.POST.get("field")
            crop_id = request.POST.get("crop")
            season_id = request.POST.get("season")
            logger.info(
                "create_operation POST selection user_id=%s field_id=%s crop_id=%s season_id=%s",
                request.user.id,
                field_id,
                crop_id,
                season_id,
            )

            try:
                base_op.field_crop = _resolve_field_crop_for_operation(
                    request=request,
                    field_id=field_id,
                    crop_id=crop_id,
                    season_id=season_id,
                )
            except (FieldCrop.DoesNotExist, ValueError, TypeError):
                form.add_error(None, "Invalid field/crop/season combination")
                return render(request, "core/create_operation.html", _get_create_operation_context(request, form))

            resources = request.POST.getlist("resource")
            quantities = request.POST.getlist("quantity")

            resource_map = {}
            for r_id, qty in zip(resources, quantities):
                if not qty:
                    continue
                qty = float(qty)
                resource_map[r_id] = resource_map.get(r_id, 0) + qty

            if form.errors:
                return render(request, "core/create_operation.html", _get_create_operation_context(request, form))
            elif not resource_map:
                return HttpResponseForbidden("At least one resource required")
            elif not base_op.performed_by:
                return HttpResponseForbidden("Worker not selected")
            elif base_op.performed_by.role != "worker":
                return HttpResponseForbidden("Invalid worker")
            else:
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

                    if op.status == Operation.Status.DONE and _is_harvest_operation(op.type):
                        if not op.field_crop.harvest_date or item_date > op.field_crop.harvest_date:
                            op.field_crop.harvest_date = item_date
                            op.field_crop.save(update_fields=["harvest_date", "updated_at"])

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
            logger.warning("create_operation form invalid: %s", form.errors)
            return render(request, "core/create_operation.html", _get_create_operation_context(request, form))

    else:
        form = OperationForm(user=request.user)

    return render(request, "core/create_operation.html", _get_create_operation_context(request, form))

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

    request.session["active_owner_id"] = owner_id

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
        "year_filter_applies_to_seasons": bool(year_param),
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
    ).select_related("field_crop__crop", "type", "performed_by").prefetch_related("operation_resources__resource")

    return render(request, "core/agronomist_operations.html", {
        "field_crop": field_crop,
        "operations": operations,
        "can_manage_operations": bool(link and link.can_manage_operations),
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
@require_POST
def toggle_agronomist_permission(request, pk, permission_name):
    if request.user.role != "owner":
        return JsonResponse({"success": False}, status=403)

    allowed_permissions = {
        "finance": "can_view_finances",
        "operations": "can_manage_operations",
        "seasons": "can_manage_seasons",
        "field-crops": "can_manage_field_crops",
    }
    field_name = allowed_permissions.get(permission_name)
    if not field_name:
        return JsonResponse({"success": False}, status=404)

    link = get_object_or_404(
        AgronomistAssignment,
        pk=pk,
        owner=request.user,
    )

    current_value = getattr(link, field_name)
    setattr(link, field_name, not current_value)
    link.save(update_fields=[field_name])

    return JsonResponse({
        "success": True,
        "permission": permission_name,
        "value": getattr(link, field_name),
    })


@login_required
def create_season(request):
    owner = get_active_owner_for_user(request.user, request)
    if not owner or not can_manage_seasons_for_owner(request.user, owner):
        return HttpResponseForbidden("You are not allowed to create seasons")

    next_url = request.GET.get("next") or request.POST.get("next") or "fields-list"

    if request.method == "POST":
        form = SeasonCreateForm(request.POST)
        if form.is_valid():
            season = form.save(commit=False)
            season.owner = owner
            if Season.objects.filter(
                owner=owner,
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
        "form_title": "Создать сезон",
        "submit_label": "Создать сезон",
    })


@login_required
def edit_season(request, pk):
    season = _get_manageable_season_or_404(request, pk) if request.user.role == "admin" else get_user_season_or_404(request.user, pk)
    if not season or not can_manage_seasons_for_owner(request.user, season.owner):
        return HttpResponseForbidden("You are not allowed to edit this season")

    default_next_url = reverse("fields-list")
    first_field_crop = season.field_crops.select_related("field").first()
    if first_field_crop:
        default_next_url = f"{reverse('field-detail', args=[first_field_crop.field_id])}?season={season.id}"
    next_url = request.GET.get("next") or request.POST.get("next") or default_next_url
    if request.method == "POST":
        form = SeasonCreateForm(request.POST, instance=season)
        if form.is_valid():
            season = form.save(commit=False)
            try:
                season.save()
            except (IntegrityError, ValidationError) as exc:
                message = "Season already exists" if isinstance(exc, IntegrityError) else "; ".join(exc.messages)
                messages.error(request, message)
            else:
                messages.success(request, f"Season '{season}' updated successfully.")
                return redirect(next_url)
    else:
        form = SeasonCreateForm(instance=season)

    return render(request, "core/create_season.html", {
        "form": form,
        "next": next_url,
        "form_title": "Редактировать сезон",
        "submit_label": "Сохранить изменения",
    })


@login_required
@require_POST
def delete_season(request, pk):
    season = _get_manageable_season_or_404(request, pk) if request.user.role == "admin" else get_user_season_or_404(request.user, pk)
    if not season or not can_manage_seasons_for_owner(request.user, season.owner):
        return HttpResponseForbidden("You are not allowed to delete this season")

    next_url = request.POST.get("next") or reverse("fields-list")
    season.delete()
    messages.success(request, "Season deleted.")
    return redirect(next_url)


@login_required
def create_field_crop(request):
    owner = get_active_owner_for_user(request.user, request)
    if request.user.role != "admin" and (not owner or not can_manage_field_crops_for_owner(request.user, owner)):
        return HttpResponseForbidden("You are not allowed to create field crops")

    next_url = request.GET.get("next") or request.POST.get("next")
    preselect_field_id = request.GET.get("field") or request.POST.get("field")
    preselect_season_id = request.GET.get("season") or request.POST.get("season")

    if request.method == "POST":
        form = FieldCropCreateForm(request.POST, user=request.user)
        if form.is_valid():
            field_crop = form.save()
            messages.success(request, "Crop added to field.")
            if next_url:
                return redirect(next_url)
            detail_url = reverse("field-detail", args=[field_crop.field_id])
            return redirect(f"{detail_url}?season={field_crop.season_id}")
    else:
        initial = {}
        if preselect_field_id:
            initial["field"] = preselect_field_id
        if preselect_season_id:
            initial["season"] = preselect_season_id
        form = FieldCropCreateForm(initial=initial, user=request.user)

    return render(
        request,
        "core/create_field_crop.html",
        _get_field_crop_form_context(
            request,
            form,
            next_url=next_url or "",
            preselect_field_id=preselect_field_id or "",
            preselect_season_id=preselect_season_id or "",
            form_title="Добавить культуру",
            submit_label="Добавить культуру",
        ),
    )


@login_required
def edit_field_crop(request, pk):
    field_crop = _get_manageable_field_crop_or_404(request, pk) if request.user.role == "admin" else get_user_field_crop_or_404(request.user, pk)
    if not field_crop or not can_manage_field_crops_for_owner(request.user, field_crop.field.owner):
        return HttpResponseForbidden("You are not allowed to edit this field crop")

    next_url = request.GET.get("next") or request.POST.get("next") or f"{reverse('field-detail', args=[field_crop.field_id])}?season={field_crop.season_id}"
    if request.method == "POST":
        form = FieldCropCreateForm(request.POST, instance=field_crop, user=request.user)
        if form.is_valid():
            field_crop = form.save()
            messages.success(request, "Crop assignment updated.")
            return redirect(next_url)
    else:
        form = FieldCropCreateForm(instance=field_crop, user=request.user)

    return render(
        request,
        "core/create_field_crop.html",
        _get_field_crop_form_context(
            request,
            form,
            next_url=next_url,
            preselect_field_id=str(field_crop.field_id),
            preselect_season_id=str(field_crop.season_id),
            form_title="Редактировать культуру",
            submit_label="Сохранить изменения",
        ),
    )


@login_required
@require_POST
def delete_field_crop(request, pk):
    field_crop = _get_manageable_field_crop_or_404(request, pk) if request.user.role == "admin" else get_user_field_crop_or_404(request.user, pk)
    if not field_crop or not can_manage_field_crops_for_owner(request.user, field_crop.field.owner):
        return HttpResponseForbidden("You are not allowed to delete this field crop")

    next_url = request.POST.get("next") or f"{reverse('field-detail', args=[field_crop.field_id])}?season={field_crop.season_id}"
    field_crop.delete()
    messages.success(request, "Crop assignment deleted.")
    return redirect(next_url)


# ─────────────────────────────────────────────
# FIELDS — entry point
# ─────────────────────────────────────────────

@login_required
def field_list_view(request):
    """Fields-first entry point for owners and agronomists."""
    today = now().date()

    if request.user.role == "agronomist":
        active_owner_id = request.session.get("active_owner_id")
        owner_ids = AgronomistAssignment.objects.filter(
            agronomist=request.user
        ).values_list("owner_id", flat=True)
        if active_owner_id and active_owner_id in owner_ids:
            owner_ids = [active_owner_id]
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
            if fc.get_computed_status() == FieldCrop.Status.ACTIVE
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
            field=field, season__year=selected_season.year
        ).prefetch_related(
            "operations__operation_resources__resource",  # Block D
            "operations__performed_by",
            "operations__type",
        ).select_related("crop")

        operations_by_id = {}
        for fc in fcs:
            ops_qs = list(
                Operation.objects.filter(
                    field_crop__field_id=fc.field_id,
                    field_crop__crop_id=fc.crop_id,
                    field_crop__season__year=selected_season.year
                ).select_related("performed_by", "type")
            )
            field_crops.append({
                "fc": fc,
                "computed_status": fc.get_computed_status(),
                "ops_total": len(ops_qs),
                "ops_done": sum(1 for o in ops_qs if o.status == "done"),
            })
            for op in ops_qs:
                operations_by_id[op.id] = op

        # Sort operations by date descending
        operations_for_season = sorted(operations_by_id.values(), key=lambda o: o.date, reverse=True)

    return render(request, "core/field_detail.html", {
        "field": field,
        "active_seasons": active_seasons,
        "past_seasons": past_seasons,
        "future_seasons": future_seasons,
        "selected_season": selected_season,
        "field_crops": field_crops,
        "operations": operations_for_season,
        "is_owner": request.user.role == "owner",
        "status_active": FieldCrop.Status.ACTIVE,
        "status_harvested": FieldCrop.Status.HARVESTED,
        "can_manage_operations": can_manage_operations_for_owner(request.user, field.owner),
        "can_manage_seasons": can_manage_seasons_for_owner(request.user, field.owner),
        "can_manage_field_crops": can_manage_field_crops_for_owner(request.user, field.owner),
    })
