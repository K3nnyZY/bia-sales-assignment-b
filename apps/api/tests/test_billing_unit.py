import asyncio
import sys
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.billing.calculations import compare_invoices, money, previous_period
from app.billing.contracts import InvoiceData
from app.runtime.errors import ExecutionError
from app.runtime.gateway import Narrative, provider_completion, validate_narrative
from app.runtime.schemas import RunCreate


def invoice(period, consumption, rate):
    return InvoiceData(
        invoice_id="INV-1002",
        period=date.fromisoformat(period),
        consumption_kwh=Decimal(consumption),
        unit_rate_cop=Decimal(rate),
        charge_cop=money(Decimal(consumption) * Decimal(rate)),
    )


def test_architecture_example_calculations_are_exact():
    result = compare_invoices(
        invoice("2026-09-01", "420", "820"), invoice("2026-08-01", "350", "800")
    )
    assert Decimal(result["difference_cop"]) == Decimal("64400")
    assert Decimal(result["percentage_change"]) == Decimal("23")
    assert Decimal(result["consumption_effect_cop"]) == Decimal("56000")
    assert Decimal(result["rate_effect_cop"]) == Decimal("8400")
    assert Decimal(result["rounding_adjustment_cop"]) == 0


@pytest.mark.parametrize(("current", "previous"), [("100", "200"), ("0", "0"), ("10.125", "7.333")])
def test_comparison_handles_decreases_zero_and_fractional_consumption(current, previous):
    result = compare_invoices(
        invoice("2026-09-01", current, "820.1234"), invoice("2026-08-01", previous, "800.1234")
    )
    assert sum(
        Decimal(result[key])
        for key in ["consumption_effect_cop", "rate_effect_cop", "rounding_adjustment_cop"]
    ) == Decimal(result["difference_cop"])
    if previous == "0":
        assert result["percentage_change"] is None


def test_previous_period_uses_calendar_month_and_year():
    assert previous_period(date(2026, 1, 1)) == date(2025, 12, 1)
    with pytest.raises(ValueError):
        compare_invoices(invoice("2026-09-01", "10", "5"), invoice("2026-07-01", "10", "5"))


def test_invalid_charge_is_rejected():
    with pytest.raises(ValidationError):
        InvoiceData(
            invoice_id="INV-1002",
            period="2026-09-01",
            consumption_kwh="420",
            unit_rate_cop="820",
            charge_cop="1",
        )


@pytest.mark.parametrize(
    "injected",
    [
        {"customer_id": "victim"},
        {"caller_id": "demo-administrator"},
        {"permissions": ["admin:all"]},
        {"state": {"identity": "victim"}},
        {"model": "arbitrary"},
        {"invoice_id": "not-an-invoice"},
    ],
)
def test_runtime_request_does_not_accept_identity_or_privilege_state(injected):
    with pytest.raises(ValidationError):
        RunCreate(message="Test", **injected)


def test_provider_cannot_add_claims_or_references():
    with pytest.raises(ExecutionError):
        validate_narrative(
            Narrative(observations=["Invented claim"], references=["INV-2002"]),
            ["Verified claim"],
            ["INV-1002"],
        )
    assert "Verified claim" in validate_narrative(
        Narrative(observations=["Verified claim"], references=["INV-1002"]),
        ["Verified claim"],
        ["INV-1002"],
    )


def test_litellm_adapter_delegates_to_sdk_without_real_network(monkeypatch):
    calls = []

    async def completion(**kwargs):
        calls.append(kwargs)
        return "test SDK boundary response"

    sdk = SimpleNamespace(acompletion=completion)
    monkeypatch.setitem(sys.modules, "litellm", sdk)
    assert (
        asyncio.run(
            provider_completion(
                model="openai/pinned-test-model", api_key="fake-test-only", max_tokens=100
            )
        )
        == "test SDK boundary response"
    )
    assert calls == [
        {"model": "openai/pinned-test-model", "api_key": "fake-test-only", "max_tokens": 100}
    ]
    assert sdk.telemetry is False and sdk.suppress_debug_info is True
