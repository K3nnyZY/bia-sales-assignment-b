from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.catalogs.schemas import Contract

Money = Annotated[Decimal, Field(ge=0, le=Decimal("9999999999999999.99"))]
InvoiceId = Annotated[str, Field(pattern=r"^INV-[0-9]{4,12}$")]


class InvoiceInput(Contract):
    invoice_id: InvoiceId


class InvoiceData(Contract):
    invoice_id: str
    period: date
    currency: Literal["COP"] = "COP"
    consumption_kwh: Money
    unit_rate_cop: Money
    charge_cop: Money

    @model_validator(mode="after")
    def consistent_amount(self):
        expected = (self.consumption_kwh * self.unit_rate_cop).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if self.charge_cop != expected:
            raise ValueError("Invoice charge does not match consumption and rate")
        if self.period.day != 1:
            raise ValueError("Invoice period must be a calendar month")
        return self


class KnowledgeInput(Contract):
    period: date


class KnowledgeItem(Contract):
    id: str
    version: str
    kind: Literal["tariff", "faq"]
    title: str
    content: Annotated[str, Field(max_length=6000)]
    valid_from: date
    valid_to: date


class KnowledgeResult(Contract):
    items: Annotated[list[KnowledgeItem], Field(min_length=1, max_length=10)]


# Known adapter versions are bound to these exact registered schemas.
ADAPTERS = {
    "invoice-lookup-v3": ("get_customer_invoice", "3.0.0", InvoiceInput, InvoiceData),
    "invoice-previous-v1": ("get_previous_invoice", "1.0.0", InvoiceInput, InvoiceData),
    "billing-knowledge-v1": ("search_billing_knowledge", "1.0.0", KnowledgeInput, KnowledgeResult),
}
