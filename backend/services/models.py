"""Public options shared by synchronous, playground and queued services."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TranslationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_language: Literal["auto", "ar", "en"] = "auto"
    target_language: Literal["ar", "en"] = "ar"
    glossary: dict[str, str] = Field(default_factory=dict, max_length=100)
    preserve_names: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def different_languages(self):
        if self.source_language == self.target_language:
            raise ValueError("Source and target languages must differ")
        if any(
            not key.strip() or not value.strip() or len(key) > 200 or len(value) > 200
            for key, value in self.glossary.items()
        ):
            raise ValueError("Glossary entries must contain 1–200 characters")
        if any(not name.strip() or len(name) > 200 for name in self.preserve_names):
            raise ValueError("Preserved names must contain 1–200 characters")
        return self


class FinancialOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tax_rate: Decimal | None = Field(None, ge=0, le=1, description="Fraction, e.g. 0.15; no assumed default")
    tolerance: Decimal = Field(Decimal("0.01"), ge=0, le=100)
    decimal_places: int = Field(2, ge=0, le=4)
    date_order: Literal["DMY", "MDY"] | None = None
    tax_inclusive: bool = False


class DocumentRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z_][A-Za-z0-9_.]*$")
    operator: Literal["required", "eq", "neq", "gte", "lte", "in", "contains"]
    value: Any = None
    severity: Literal["warning", "error"] = "error"
    message: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def operand(self):
        if self.operator == "in" and not isinstance(self.value, list):
            raise ValueError("The 'in' rule requires a list of allowed values")
        if self.operator in {"gte", "lte"}:
            from backend.services.normalization import decimal_value

            if decimal_value(self.value) is None:
                raise ValueError("Numeric rules require a valid numeric value")
        if self.operator == "contains" and not isinstance(self.value, str):
            raise ValueError("The 'contains' rule requires text")
        return self


class ServiceOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    financial: FinancialOptions = Field(default_factory=FinancialOptions)
    translation: TranslationOptions = Field(default_factory=TranslationOptions)
    reference_document_id: str | None = Field(None, max_length=200)
    reference_text: str | None = Field(None, max_length=500_000)
    rules: list[DocumentRule] = Field(default_factory=list, max_length=100)
    rule_set_id: str | None = Field(None, max_length=100)
    guardian: bool = Field(default=True, description="When True, Guardian verifies schema and evidence citations. When False, returns raw extracted values directly.")

    @model_validator(mode="after")
    def one_reference(self):
        if self.reference_document_id and self.reference_text:
            raise ValueError("Provide reference_document_id or reference_text, not both")
        return self


class ServiceRequest(BaseModel):
    service: str = "summary"
    document_id: str | None = Field(None, max_length=200)
    text_content: str | None = Field(None, max_length=500_000)
    query: str | None = Field(None, max_length=20_000)
    system_prompt: str | None = Field(None, max_length=30_000)
    schema_override: dict | None = None
    output_format: Literal["json", "markdown", "auto"] = "auto"
    model: str | None = None
    temperature: float | None = Field(None, ge=0, le=2)
    guardian: bool = Field(default=True, description="When True, Guardian verifies schema and evidence citations. When False, returns value directly.")
    webhook_url: str | None = None
    options: ServiceOptions = Field(default_factory=ServiceOptions)

    @model_validator(mode="after")
    def valid_input(self):
        if bool(self.document_id) == bool(self.text_content and self.text_content.strip()):
            raise ValueError("Provide exactly one of document_id or non-empty text_content")
        from backend.services.contracts import compile_override

        compile_override(self.schema_override)
        if self.service.lower().replace("-", "_") in {"invoice_matching", "contract_comparison"}:
            if not self.options.reference_document_id and not (
                self.options.reference_text and self.options.reference_text.strip()
            ):
                raise ValueError("This service requires a reference document or reference text")
        return self


class SourceCitation(BaseModel):
    documentId: str
    document: str
    page: int = Field(ge=1)
    quote: str


class ContractChange(BaseModel):
    type: Literal["modified", "removed", "added"]
    categories: list[str]
    before: str | None
    after: str | None
    beforeSources: list[SourceCitation]
    afterSources: list[SourceCitation]


class ContractComparisonReport(BaseModel):
    status: Literal["changed", "unchanged"]
    change_count: int = Field(ge=0)
    changes: list[ContractChange]
    comparison_method: Literal["normalized_line_diff"]
    limitations: str


class InvoiceMatchingReport(BaseModel):
    status: Literal["matched", "needs_review"]
    matched_items: list[dict]
    differences: list[dict]
    invoice: dict
    purchase_order: dict
