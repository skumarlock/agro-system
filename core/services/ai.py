from decimal import Decimal

from django.db.models import Sum

from core.models import Operation, OperationResource, Resource


def ask_external_llm(owner, prompt):
    config = getattr(owner, "ai_config", None)
    if not config or not config.ai_enabled or config.token_balance <= 0:
        return None
    return None


def build_ai_chat_reply(owner, prompt):
    external_reply = ask_external_llm(owner, prompt)
    if external_reply:
        return external_reply

    alerts = get_rule_based_alerts(owner)
    if alerts:
        alert_text = "\n".join(f"- {alert}" for alert in alerts)
    else:
        alert_text = "- Критичных предупреждений по текущим данным нет."

    return (
        "AI-чат пока работает в режиме заготовки без внешнего API.\n\n"
        "Чтобы подключить нейросеть, реализуйте вызов провайдера в "
        "`core.services.ai.ask_external_llm(owner, prompt)` и включите AI "
        "в `OwnerAIConfig`.\n\n"
        f"Ваш запрос: {prompt}\n\n"
        f"Быстрые проверки хозяйства:\n{alert_text}"
    )


def get_rule_based_alerts(owner):
    alerts = []
    water_usage = (
        OperationResource.objects.filter(
            operation__field_crop__field__owner=owner,
            resource__type=Resource.Type.WATER,
        ).aggregate(total=Sum("quantity"))["total"]
        or Decimal("0")
    )
    if water_usage > Decimal("1000"):
        alerts.append("Высокий расход воды: проверьте график полива.")

    if not Operation.objects.filter(field_crop__field__owner=owner).exists():
        alerts.append("Операций пока нет: можно начать с плана работ по активным полям.")

    return alerts
