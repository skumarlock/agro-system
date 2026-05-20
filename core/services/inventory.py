from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from core.models import Operation, Purchase, Resource, ResourcePrice, Stock, StockLog


ZERO = Decimal("0")


def resolve_resource_price(owner, resource_id):
    last_purchase = (
        Purchase.objects.filter(owner=owner, resource_id=resource_id)
        .order_by("-created_at")
        .first()
    )
    if last_purchase:
        return last_purchase.price_per_unit

    owner_price = ResourcePrice.objects.filter(owner=owner, resource_id=resource_id).first()
    if owner_price:
        return owner_price.price

    return Resource.objects.get(pk=resource_id).cost_per_unit


@transaction.atomic
def create_purchase(*, owner, resource, quantity, price_per_unit, supplier=""):
    purchase = Purchase.objects.create(
        owner=owner,
        resource=resource,
        quantity=quantity,
        price_per_unit=price_per_unit,
        supplier=supplier or "",
    )
    _adjust_stock(
        owner=owner,
        resource=resource,
        delta=quantity,
        source_type=StockLog.SourceType.PURCHASE,
        source_id=purchase.pk,
    )
    return purchase


@transaction.atomic
def manual_adjust_stock(*, owner, resource, new_quantity):
    stock, _ = Stock.objects.select_for_update().get_or_create(
        owner=owner,
        resource=resource,
        defaults={"quantity_current": ZERO},
    )
    delta = Decimal(new_quantity) - stock.quantity_current
    if delta:
        _adjust_stock(
            owner=owner,
            resource=resource,
            delta=delta,
            source_type=StockLog.SourceType.MANUAL,
            source_id=None,
        )
    return stock


@transaction.atomic
def sync_operation_stock(operation: Operation):
    owner = operation.field_crop.field.owner
    items = {
        item.resource_id: item
        for item in operation.operation_resources.select_related("resource")
    }
    logged_resource_ids = StockLog.objects.filter(
        owner=owner,
        source_type=StockLog.SourceType.OPERATION,
        source_id=operation.pk,
    ).values_list("resource_id", flat=True)
    resource_ids = set(items) | set(logged_resource_ids)

    for resource_id in resource_ids:
        item = items.get(resource_id)
        current_delta = (
            StockLog.objects.filter(
                owner=owner,
                resource_id=resource_id,
                source_type=StockLog.SourceType.OPERATION,
                source_id=operation.pk,
            ).aggregate(total=Sum("delta"))["total"]
            or ZERO
        )
        target_delta = -item.quantity if item and operation.status == Operation.Status.DONE else ZERO
        adjustment = target_delta - current_delta
        if adjustment:
            _adjust_stock(
                owner=owner,
                resource=item.resource if item else Resource.objects.get(pk=resource_id),
                delta=adjustment,
                source_type=StockLog.SourceType.OPERATION,
                source_id=operation.pk,
            )


def get_stock_warnings(owner, resource_map):
    resource_ids = [int(resource_id) for resource_id in resource_map]
    stocks = {
        stock.resource_id: stock.quantity_current
        for stock in Stock.objects.filter(owner=owner, resource_id__in=resource_ids)
    }
    warnings = []
    for resource_id, required in resource_map.items():
        if int(resource_id) not in stocks:
            continue
        current = stocks[int(resource_id)]
        required_decimal = Decimal(str(required))
        if current < required_decimal:
            resource = Resource.objects.filter(pk=resource_id).first()
            name = resource.name if resource else f"#{resource_id}"
            warnings.append((name, current, required_decimal))
    return warnings


def _adjust_stock(*, owner, resource, delta, source_type, source_id):
    delta = Decimal(delta)
    stock, _ = Stock.objects.select_for_update().get_or_create(
        owner=owner,
        resource=resource,
        defaults={"quantity_current": ZERO},
    )
    stock.quantity_current += delta
    stock.save(update_fields=["quantity_current", "updated_at"])
    StockLog.objects.create(
        owner=owner,
        resource=resource,
        delta=delta,
        source_type=source_type,
        source_id=source_id,
    )
    return stock
