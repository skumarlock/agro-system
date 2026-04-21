from django import template
from core.services.currency import get_usd_rate

register = template.Library()


@register.filter
def money(value):
    try:
        value = float(value)
        formatted = f"{value:,.0f}".replace(",", " ")
        return f"{formatted} сум"
    except:
        return value

@register.filter
def money_usd(value):
    try:
        rate = get_usd_rate()
        value = float(value) / float(rate)
        return f"{value:,.0f}".replace(",", " ") + " $"
    except:
        return value

@register.filter
def number(value):
    try:
        value = float(value)
        return f"{value:,.2f}".replace(",", " ")
    except:
        return value

@register.filter
def money_short(value):
    try:
        value = float(value)

        if value >= 1_000_000:
            short = value / 1_000_000
            return f"{short:.1f}".rstrip("0").rstrip(".") + " млн"
        elif value >= 1_000:
            short = value / 1_000
            return f"{short:.1f}".rstrip("0").rstrip(".") + " тыс"
        else:
            return str(int(value))

    except:
        return value