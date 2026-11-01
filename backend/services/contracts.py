"""Service output contracts and JSON Schema enforcement (not prompt-only validation)."""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from backend.services.normalization import decimal_value, detect_currency, normalize_date, normalize_digits


class OutputValidationError(ValueError):
    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__("Service output failed validation")


def nullable(kind: str, **kwargs) -> dict:
    return {"type": [kind, "null"], **kwargs}


S = nullable("string")
N = nullable("number")
RATE = nullable("number", minimum=0, maximum=1)
B = nullable("boolean")
PARTY = {
    "anyOf": [
        {"type": "string"},
        {
            "type": "object",
            "properties": {
                key: S
                for key in [
                    "name",
                    "address",
                    "city",
                    "country",
                    "postal_code",
                    "email",
                    "phone",
                    "tax_id",
                    "iban",
                    "swift",
                ]
            },
        },
        {"type": "null"},
    ]
}
ITEM = {
    "type": "object",
    "properties": {
        "description": S,
        "sku": S,
        "quantity": N,
        "unit_price": N,
        "amount": N,
        "tax_rate": RATE,
    },
}
A = nullable("array", items={"type": ["object", "string", "null"]})

FIELDS = {
    "invoice": {
        "vendor": PARTY,
        "client": PARTY,
        "invoice_number": S,
        "invoice_date": S,
        "due_date": S,
        "currency": S,
        "line_items": nullable("array", items=ITEM),
        "subtotal": N,
        "tax_total": N,
        "tax_rate": RATE,
        "discount": N,
        "shipping": N,
        "total": N,
        "payment_terms": PARTY,
        "po_number": S,
        "notes": S,
    },
    "receipt": {
        "merchant": PARTY,
        "date": S,
        "currency": S,
        "receipt_number": S,
        "line_items": nullable("array", items=ITEM),
        "subtotal": N,
        "tax_total": N,
        "tip": N,
        "discount": N,
        "total": N,
        "payment_method": S,
    },
    "contract": {
        "parties": A,
        "effective_date": S,
        "expiration_date": S,
        "governing_law": S,
        "clauses": {"type": ["array", "object", "null"]},
        "obligations": A,
        "payment_terms": PARTY,
        "renewal_terms": PARTY,
        "risks": A,
    },
    "resume": {"name": S, "contact": PARTY, "skills": A, "experience": A, "education": A},
    "compliance": {"findings": A, "recommendations": A},
    "form_parser": {"fields": {"type": ["object", "array", "null"]}, "checkboxes": A, "signatures": A},
    "financial_statement": {
        "currency": S,
        "financial_ratios": nullable("object"),
        "metrics": {
            "type": "object",
            "properties": {
                name: N
                for name in [
                    "revenue",
                    "cogs",
                    "gross_profit",
                    "operating_expenses",
                    "operating_income_ebit",
                    "net_income",
                    "total_assets",
                    "total_liabilities",
                    "equity",
                ]
            },
        },
    },
    "redaction": {"redacted_text": S, "findings": A},
    "classifier": {"document_type": S, "language": S, "department": S, "urgency": S},
    "translation": {"translated_text": {"type": "string", "minLength": 1}, "terminology_notes": A},
    "anomaly_audit": {
        "subtotal": N,
        "tax_total": N,
        "discount": N,
        "total": N,
        "invoice_date": S,
        "due_date": S,
        "line_items": nullable("array", items=ITEM),
    },
}

ALIASES = {
    "invoice": {
        "total_amount": "total",
        "tax_amount": "tax_total",
        "tax_total_amount": "tax_total",
        "issue_date": "invoice_date",
        "items": "line_items",
    },
    "receipt": {
        "merchant_name": "merchant",
        "grand_total": "total",
        "tax_amount": "tax_total",
        "taxes": "tax_total",
        "items": "line_items",
        "transaction_date": "date",
    },
    "contract": {"key_clauses": "clauses", "risk_flags": "risks", "expiration": "expiration_date"},
    "resume": {"candidate_name": "name", "work_history": "experience", "work_experience": "experience"},
    "classifier": {
        "category": "document_type",
        "primary_language": "language",
        "primary_lang": "language",
        "routing_department": "department",
    },
    "anomaly_audit": {"tax_amount": "tax_total", "tax": "tax_total", "issue_date": "invoice_date"},
}


def service_schema(service: str) -> dict | None:
    fields = FIELDS.get(service)
    if not fields:
        return None
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": copy.deepcopy(fields),
        "required": list(fields),
        "additionalProperties": False,
    }


def parse_json(text: str) -> Any:
    """Read a whole JSON result or a complete fenced result, never a nested salvage object."""
    import re

    if not isinstance(text, str):
        return None

    def reject_constant(value):
        raise ValueError(f"Non-JSON numeric constant: {value}")

    stripped = text.strip()
    decoder = json.JSONDecoder(parse_float=Decimal, parse_constant=reject_constant)
    try:
        return json.loads(stripped, parse_float=Decimal, parse_constant=reject_constant)
    except (ValueError, TypeError):
        pass
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped, re.I)
    if fenced:
        try:
            return json.loads(fenced.group(1), parse_float=Decimal, parse_constant=reject_constant)
        except ValueError:
            return None
    candidates = [position for position in (stripped.find("{"), stripped.find("[")) if position >= 0]
    if candidates:
        try:
            value, _ = decoder.raw_decode(stripped[min(candidates) :])
            return value if isinstance(value, (dict, list)) else None
        except ValueError:
            return None
    return None


def compile_override(schema: Any) -> dict | None:
    if schema is None:
        return None
    if not isinstance(schema, dict):
        raise ValueError("schema_override must be a JSON Schema object or an example object")
    if any(
        key in schema
        for key in (
            set(Draft202012Validator.VALIDATORS) | {"$schema", "$defs", "$id", "$anchor", "$ref", "$dynamicRef"}
        )
    ):
        result = copy.deepcopy(schema)
    else:
        # Backwards-compatible example templates are converted into an actual schema.
        def infer(value):
            if isinstance(value, dict):
                return {
                    "type": "object",
                    "properties": {k: infer(v) for k, v in value.items()},
                    "required": list(value),
                }
            if isinstance(value, list):
                return {"type": "array", "items": infer(value[0]) if value else {}}
            if value is None:
                return {}
            if isinstance(value, str):
                descriptors = {
                    "str": "string",
                    "string": "string",
                    "float": "number",
                    "number": "number",
                    "int": "integer",
                    "integer": "integer",
                    "bool": "boolean",
                    "boolean": "boolean",
                    "dict": "object",
                    "object": "object",
                    "list": "array",
                    "array": "array",
                }
                if value.lower() in descriptors:
                    return {"type": descriptors[value.lower()]}
            return {
                "type": "boolean"
                if isinstance(value, bool)
                else "number"
                if isinstance(value, (int, float))
                else "string"
            }

        result = infer(schema)

    # Resolve only local references; client schemas cannot perform network/file reads.
    def check_refs(node):
        if isinstance(node, dict):
            if "$ref" in node and (not isinstance(node["$ref"], str) or not node["$ref"].startswith("#")):
                raise ValueError("Only local JSON Schema references are supported")
            if "$dynamicRef" in node:
                raise ValueError("Dynamic JSON Schema references are not supported")
            for child in node.values():
                check_refs(child)
        elif isinstance(node, list):
            for child in node:
                check_refs(child)

    check_refs(result)
    try:
        Draft202012Validator.check_schema(result)
    except SchemaError as exc:
        raise ValueError(f"Invalid JSON Schema: {exc.message}") from exc
    return result


def validate_schema(data: Any, schema: dict) -> None:
    errors = [
        {"field": ".".join(map(str, error.absolute_path)), "reason": error.message}
        for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data)
    ]
    if errors:
        raise OutputValidationError(errors[:50])


def prepare_data(service: str, data: Any, source_text: str, date_order=None) -> tuple[dict, dict]:
    if not isinstance(data, dict):
        raise OutputValidationError([{"field": "", "reason": "Expected a JSON object"}])
    data = copy.deepcopy(data)
    for alias, canonical in ALIASES.get(service, {}).items():
        if canonical not in data and alias in data:
            data[canonical] = data[alias]
        if alias != canonical:
            data.pop(alias, None)
    fields = FIELDS.get(service, {})
    if fields:
        if not any(key in data and data[key] is not None for key in fields):
            raise OutputValidationError([{"field": "", "reason": "No recognized service fields were returned"}])
        for name in fields:
            data.setdefault(name, None)
    originals = {}
    numbers = {
        "quantity",
        "unit_price",
        "amount",
        "subtotal",
        "tax_total",
        "total",
        "discount",
        "shipping",
        "tip",
        "revenue",
        "cogs",
        "gross_profit",
        "operating_expenses",
        "operating_income_ebit",
        "net_income",
        "total_assets",
        "total_liabilities",
        "equity",
    }
    dates = {"invoice_date", "due_date", "date", "effective_date", "expiration_date"}

    def visit(node, path=""):
        if isinstance(node, dict):
            for key, value in list(node.items()):
                field = f"{path}.{key}".strip(".")
                if key == "tax_rate" and value is not None:
                    originals[field] = value
                    number = decimal_value(normalize_digits(str(value)).rstrip("%"))
                    if number is None:
                        raise OutputValidationError([{"field": field, "reason": "Invalid tax rate"}])
                    if isinstance(value, str) and "%" in normalize_digits(value):
                        number /= 100
                    node[key] = number
                elif key in numbers and value is not None:
                    number = decimal_value(value)
                    if number is None:
                        raise OutputValidationError([{"field": field, "reason": "Invalid numeric value"}])
                    originals[field] = value
                    node[key] = number
                elif key in dates and value is not None:
                    originals[field] = value
                    normalized, reason = normalize_date(value, date_order)
                    node[key] = normalized
                    if reason:
                        originals[field + ":reason"] = reason
                else:
                    visit(value, field)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                visit(value, f"{path}.{index}")

    visit(data)
    if "currency" in fields and not data.get("currency"):
        data["currency"] = detect_currency(source_text)
    if service == "financial_statement" and data["metrics"] is None:
        data["metrics"] = {name: None for name in fields["metrics"]["properties"]}
    schema = service_schema(service)
    if schema:
        validate_schema(data, schema)
    return data, originals
