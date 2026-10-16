from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.billing.contracts import InvoiceData


def previous_period(period: date) -> date:
    return (
        date(period.year - 1, 12, 1)
        if period.month == 1
        else date(period.year, period.month - 1, 1)
    )


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compare_invoices(current: InvoiceData, previous: InvoiceData) -> dict[str, str | None]:
    if previous.period != previous_period(current.period):
        raise ValueError("Comparison requires the immediately preceding month")
    difference = money(current.charge_cop - previous.charge_cop)
    consumption_effect = money(
        (current.consumption_kwh - previous.consumption_kwh) * previous.unit_rate_cop
    )
    rate_effect = money(current.consumption_kwh * (current.unit_rate_cop - previous.unit_rate_cop))
    return {
        "current_charge_cop": str(current.charge_cop),
        "previous_charge_cop": str(previous.charge_cop),
        "difference_cop": str(difference),
        "percentage_change": str(money(difference / previous.charge_cop * 100))
        if previous.charge_cop
        else None,
        "consumption_difference_kwh": str(current.consumption_kwh - previous.consumption_kwh),
        "consumption_effect_cop": str(consumption_effect),
        "rate_effect_cop": str(rate_effect),
        "rounding_adjustment_cop": str(money(difference - consumption_effect - rate_effect)),
    }
