import requests
from core.models import ExchangeRate


def update_usd_rate():
    try:
        response = requests.get(
            "https://api.exchangerate-api.com/v4/latest/UZS",
            timeout=5
        )
        data = response.json()

        usd_rate = 1 / data["rates"]["USD"]

        ExchangeRate.objects.update_or_create(
            currency="USD",
            defaults={"rate": usd_rate}
        )

    except Exception:
        pass  # не роняем систему


def get_usd_rate():
    rate = ExchangeRate.objects.filter(currency="USD").first()

    if rate:
        return rate.rate

    # fallback (если API недоступен)
    return 12500