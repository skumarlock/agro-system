def sort_resources(resources, sort, order):
    if not sort:
        return resources, "asc"

    reverse = order == "desc"

    key_map = {
        "name": lambda x: x["name"],
        "quantity": lambda x: x["quantity"],
        "cost": lambda x: x["cost"] or 0,
    }

    if sort in key_map:
        resources = sorted(resources, key=key_map[sort], reverse=reverse)

    next_order = "desc" if order == "asc" else "asc"
    return resources, next_order
