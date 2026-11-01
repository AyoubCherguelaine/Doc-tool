"""Locate evidence in original pages; do not trust model-supplied citations/confidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backend.services.normalization import decimal_value, normalize_date, normalize_digits, normalize_text


@dataclass(frozen=True)
class SourcePage:
    document_id: str
    name: str
    page: int
    text: str


def source_pages(bundle) -> list[SourcePage]:
    pages = []
    for document in bundle.pdf_docs:
        for page in document.pages:
            if isinstance(page.text, str):
                pages.append(SourcePage(str(bundle.doc_id), document.name, page.page_number, page.text))
    return pages


def find_evidence(
    value: Any, pages: list[SourcePage], original=None, date_order=None, percent=False, label=None
) -> list[dict]:
    if value is None:
        return []
    found = []
    for page in pages:
        # Keep quotes from original text, even when matching normalized Arabic digits.
        candidates = page.text.splitlines() or [page.text]
        if isinstance(value, str) and any(character.isspace() for character in value):
            candidates += ["\n".join(candidates[index : index + 4]) for index in range(len(candidates) - 1)]
        for line in candidates:
            match = False
            if isinstance(value, bool):
                if isinstance(label, str) and label.strip():
                    checked = r"(?:\[\s*[x✓✔]\s*\]|☑|✓|✔)"
                    unchecked = r"(?:\[\s*\]|☐|□)"
                    marker = checked if value else unchecked
                    label_pattern = re.escape(normalize_text(label))
                    match = (
                        re.search(
                            rf"(?:{marker}\s*{label_pattern}|{label_pattern}\s*[:：]?\s*{marker})", normalize_text(line)
                        )
                        is not None
                    )
            elif isinstance(value, (int, float, Decimal)):
                patterns = [
                    r"(?<![\w])[-(]?[٠-٩۰-۹0-9]+(?:[.,٬٫ ][٠-٩۰-۹0-9]+)*\)?",
                    r"(?<![\w])[-(]?[٠-٩۰-۹0-9]+(?:[.,٬٫][٠-٩۰-۹0-9]+)*\)?",
                ]
                tokens = [
                    matched.group()
                    for pattern in patterns
                    for matched in re.finditer(pattern, line)
                    if percent or not line[matched.end() :].lstrip().startswith(("%", "٪"))
                ]
                match = any(decimal_value(token) == decimal_value(value) for token in tokens)
                if percent:
                    rates = re.findall(r"(\d+(?:\.\d+)?)\s*%", normalize_digits(line))
                    match = match or any(decimal_value(rate) / 100 == decimal_value(value) for rate in rates)
            elif isinstance(value, str):
                needle = normalize_text(str(original if original is not None else value))
                match = bool(needle) and needle in normalize_text(line)
                if not match and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    tokens = re.findall(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", normalize_digits(line))
                    match = any(normalize_date(token, date_order)[0] == value for token in tokens)
                if not match and len(value) == 3:
                    from backend.services.normalization import detect_currency

                    match = detect_currency(line) == value
            if match:
                found.append(
                    {"documentId": page.document_id, "document": page.name, "page": page.page, "quote": line.strip()}
                )
                break
    return found[:5]


def attach_evidence(data: dict, pages: list[SourcePage], originals: dict, date_order=None) -> list[dict]:
    records = []
    # These fields are interpretations, classifications or generated content, not extracted literals.
    generated = {
        "risks",
        "findings",
        "recommendations",
        "document_type",
        "language",
        "department",
        "urgency",
        "translated_text",
        "terminology_notes",
        "redacted_text",
        "financial_ratios",
        "summary",
        "confidence",
    }

    def visit(node, path=""):
        if isinstance(node, dict):
            for key, value in list(node.items()):
                field = f"{path}.{key}".strip(".")
                if key in generated:
                    continue
                if isinstance(value, (dict, list)):
                    visit(value, field)
                    continue
                original = originals.get(field, value)
                label = (
                    (node.get("label") or node.get("name") or node.get("field"))
                    if key in {"checked", "selected", "is_checked", "value"}
                    else None
                )
                sources = find_evidence(value, pages, original, date_order, percent=key == "tax_rate", label=label)
                reason = originals.get(field + ":reason")
                if not sources and value is not None:
                    node[key] = None
                records.append(
                    {
                        "field": field,
                        "value": node[key],
                        "originalValue": original,
                        "status": "supported" if sources else "missing" if original is None else "unverified",
                        "reason": None
                        if sources
                        else reason or ("not_provided" if original is None else "not_found_in_source"),
                        "sources": sources,
                    }
                )
        elif isinstance(node, list):
            for index, value in enumerate(list(node)):
                field = f"{path}.{index}"
                if isinstance(value, (dict, list)):
                    visit(value, field)
                else:
                    sources = find_evidence(value, pages, date_order=date_order)
                    if not sources:
                        node[index] = None
                    records.append(
                        {
                            "field": field,
                            "value": node[index],
                            "originalValue": value,
                            "status": "supported" if sources else "unverified",
                            "reason": None if sources else "not_found_in_source",
                            "sources": sources,
                        }
                    )

    visit(data)
    return records


def attach_finding_evidence(data: dict, pages: list[SourcePage]) -> list[dict]:
    """Ground detected sensitive values without treating generated risk descriptions as quotes."""
    records = []
    findings = data.get("findings") or []
    for index, finding in enumerate(findings):
        path = f"findings.{index}"
        if isinstance(finding, dict):
            key = next(
                (
                    name
                    for name in (
                        "value",
                        "matched_text",
                        "original_text",
                        "original_value",
                        "detected_value",
                        "quote",
                        "source_quote",
                        "text",
                    )
                    if finding.get(name) is not None
                ),
                None,
            )
            value = finding.get(key) if key else None
            sources = find_evidence(value, pages)
            if key and not sources:
                finding[key] = None
            finding["evidence_status"] = "supported" if sources else "unverified"
            path += f".{key}" if key else ""
        else:
            value = finding
            sources = find_evidence(value, pages)
            if not sources:
                findings[index] = None
        records.append(
            {
                "field": path,
                "value": value if sources else None,
                "originalValue": value,
                "status": "supported" if sources else "unverified",
                "sources": sources,
                "reason": None if sources else "not_found_in_source" if value is not None else "no_source_value",
            }
        )
    return records
