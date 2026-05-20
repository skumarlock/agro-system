from datetime import timedelta
from decimal import Decimal


def get_field_weather(field):
    base_temp = Decimal("26.0")
    precipitation = Decimal("0.0")
    if field.latitude is not None and field.longitude is not None:
        base_temp += (abs(field.latitude) % 5) / Decimal("10")
        precipitation = (abs(field.longitude) % 3) / Decimal("10")

    suggestion = "План работ без ограничений."
    if precipitation > Decimal("0.2"):
        suggestion = "Ожидается дождь, полив лучше перенести."

    return {
        "temp": base_temp.quantize(Decimal("0.1")),
        "precipitation": precipitation.quantize(Decimal("0.1")),
        "forecast": "stub",
        "suggestion": suggestion,
        "days": get_week_forecast(field),
    }


def get_week_forecast(field):
    from django.utils.timezone import now

    today = now().date()
    seed = int((field.pk if field else 1) or 1)
    days = []
    for i in range(7):
        rain = Decimal(((seed + i) % 4)) / Decimal("10")
        temp = Decimal("24.0") + Decimal((seed + i) % 7)
        days.append({
            "date": today + timedelta(days=i),
            "temp": temp.quantize(Decimal("0.1")),
            "precipitation": rain.quantize(Decimal("0.1")),
            "suggestion": "Полив лучше перенести" if rain > Decimal("0.2") else "Можно планировать работы",
        })
    return days
