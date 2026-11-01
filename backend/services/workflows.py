"""Cross-document matching and version comparison; every difference is inspectable."""

from __future__ import annotations

import difflib
import re
from collections import Counter

from backend.services.evidence import SourcePage
from backend.services.models import FinancialOptions
from backend.services.normalization import decimal_value, json_number, normalize_digits, normalize_text


def match_invoice(invoice: dict, order: dict, options: FinancialOptions) -> dict:
    differences, matched = [], []
    for field in ("currency", "po_number"):
        left, right = invoice.get(field), order.get(field)
        if left is None or right is None:
            differences.append(
                {
                    "field": field,
                    "status": "not_checked",
                    "reason": "missing_value",
                    "invoice": left,
                    "purchaseOrder": right,
                }
            )
        elif normalize_text(str(left)) != normalize_text(str(right)):
            differences.append({"field": field, "status": "mismatch", "invoice": left, "purchaseOrder": right})

    def index_items(items):
        indexed = {}
        for number, item in enumerate(items or []):
            identity = item.get("sku") or item.get("description")
            if not identity:
                differences.append(
                    {
                        "field": "line_items",
                        "status": "not_checked",
                        "reason": "item_without_identifier",
                        "index": number,
                    }
                )
                continue
            key = normalize_text(str(identity))
            indexed.setdefault(key, []).append((number, item))
        return indexed

    left, right = index_items(invoice.get("line_items")), index_items(order.get("line_items"))
    for key in sorted(set(left) | set(right)):
        inv, po = left.get(key, []), right.get(key, [])
        if len(inv) != 1 or len(po) != 1:
            differences.append(
                {
                    "item": key,
                    "status": "not_checked" if len(inv) > 1 or len(po) > 1 else "mismatch",
                    "reason": "duplicate_identifier" if len(inv) > 1 or len(po) > 1 else "missing_or_extra_item",
                    "invoiceIndexes": [item[0] for item in inv],
                    "purchaseOrderIndexes": [item[0] for item in po],
                }
            )
            continue
        changes = []
        for field in ("quantity", "unit_price", "amount"):
            a, b = decimal_value(inv[0][1].get(field)), decimal_value(po[0][1].get(field))
            if a is None or b is None:
                changes.append({"field": field, "status": "not_checked", "reason": "missing_value"})
            elif abs(a - b) > options.tolerance:
                changes.append(
                    {
                        "field": field,
                        "status": "mismatch",
                        "invoice": json_number(a),
                        "purchaseOrder": json_number(b),
                        "difference": json_number(a - b),
                    }
                )
        row = {"item": key, "invoiceIndex": inv[0][0], "purchaseOrderIndex": po[0][0], "differences": changes}
        if changes:
            differences.append(row)
        else:
            matched.append(row)
    if not left and not right:
        differences.append({"field": "line_items", "status": "not_checked", "reason": "no_line_items"})
    if invoice.get("currency") and order.get("currency") and invoice["currency"] == order["currency"]:
        a, b = decimal_value(invoice.get("total")), decimal_value(order.get("total"))
        if a is None or b is None:
            differences.append({"field": "total", "status": "not_checked", "reason": "missing_value"})
        elif abs(a - b) > options.tolerance:
            differences.append(
                {
                    "field": "total",
                    "status": "mismatch",
                    "invoice": json_number(a),
                    "purchaseOrder": json_number(b),
                    "difference": json_number(a - b),
                }
            )
    return {
        "status": "matched" if not differences else "needs_review",
        "matched_items": matched,
        "differences": differences,
        "invoice": invoice,
        "purchase_order": order,
    }


def compare_contracts(before: list[SourcePage], after: list[SourcePage]) -> dict:
    def lines(pages):
        return [(line.strip(), page) for page in pages for line in page.text.splitlines() if line.strip()]

    old, new = lines(before), lines(after)
    matcher = difflib.SequenceMatcher(
        a=[normalize_text(line) for line, _ in old], b=[normalize_text(line) for line, _ in new], autojunk=False
    )
    changes = []
    for operation, a, b, c, d in matcher.get_opcodes():
        if operation == "equal":
            continue
        old_text, new_text = "\n".join(line for line, _ in old[a:b]), "\n".join(line for line, _ in new[c:d])
        combined = normalize_digits(old_text + "\n" + new_text)
        categories = ["clause_text"]
        if re.search(
            r"(?:\b(?:USD|SAR|EUR|AED|DZD|amount|price|payment|fee)\b|[$€£]|ريال|مبلغ|دفع|رسوم)", combined, re.I
        ):
            categories.append("amounts_or_payment")
        if re.search(
            r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}|\b(?:date|term|renewal|expiration|days|months|years)\b|تاريخ|تجديد|مدة|أيام|أشهر|سنوات",
            combined,
            re.I,
        ):
            categories.append("dates_or_terms")
        if re.search(r"\b(?:shall|must|obligat|responsib|require)\w*|يلتزم|يجب|مسؤول|التزام", combined, re.I):
            categories.append("obligations")

        def citations(rows):
            return [
                {"documentId": page.document_id, "document": page.name, "page": page.page, "quote": line}
                for line, page in rows
            ]

        changes.append(
            {
                "type": {"replace": "modified", "delete": "removed", "insert": "added"}[operation],
                "categories": categories,
                "before": old_text or None,
                "after": new_text or None,
                "beforeSources": citations(old[a:b]),
                "afterSources": citations(new[c:d]),
            }
        )
    return {
        "status": "changed" if changes else "unchanged",
        "change_count": len(changes),
        "changes": changes,
        "comparison_method": "normalized_line_diff",
        "limitations": "Text differences are exact; category labels are keyword-based and do not assess legal effect.",
    }


def translation_checks(source: str, translated: str, options) -> dict:
    def numbers(text):
        tokens = re.findall(r"\d+(?:[.,]\d+)*", normalize_digits(text))
        return Counter(
            str(decimal_value(token).normalize()) if decimal_value(token) is not None else token for token in tokens
        )

    missing = numbers(source) - numbers(translated)
    added = numbers(translated) - numbers(source)
    problems = []
    if missing or added:
        problems.append({"check": "numbers_and_numbering", "missing": dict(missing), "unexpected": dict(added)})
    source_tokens = re.findall(r"\d+(?:[.,]\d+)*", normalize_digits(source))
    target_tokens = re.findall(r"\d+(?:[.,]\d+)*", normalize_digits(translated))

    def canonical(values):
        return [decimal_value(value) if decimal_value(value) is not None else value for value in values]

    if not missing and not added and canonical(source_tokens) != canonical(target_tokens):
        problems.append({"check": "number_sequence", "reason": "Numbers or clause numbering changed order"})
    arabic_letters = len(re.findall(r"[\u0621-\u064a]", translated))
    latin_letters = len(re.findall(r"[A-Za-z]", translated))
    if options.target_language == "ar" and arabic_letters == 0 and latin_letters >= 10:
        problems.append({"check": "target_language", "expected": "ar"})
    elif options.target_language == "en" and latin_letters == 0 and arabic_letters >= 10:
        problems.append({"check": "target_language", "expected": "en"})
    for name in options.preserve_names:
        if name in source and name not in translated:
            problems.append({"check": "preserved_name", "value": name})
    for term, target in options.glossary.items():
        if normalize_text(term) in normalize_text(source) and normalize_text(target) not in normalize_text(translated):
            problems.append({"check": "glossary", "source": term, "expected": target})
    for currency in re.findall(r"\b(?:USD|SAR|AED|EGP|DZD|EUR|GBP)\b", source):
        if currency not in translated:
            problems.append({"check": "currency_code", "value": currency})
    return {"status": "passed" if not problems else "needs_review", "issues": problems}
