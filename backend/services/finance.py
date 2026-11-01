"""Deterministic monetary checks. All arithmetic uses Decimal, never binary floats."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from backend.services.models import FinancialOptions
from backend.services.normalization import decimal_value, detect_currency, json_number, normalize_date, normalize_digits

LABELS = {
    "subtotal": ["subtotal", "sub total", "المجموع قبل الضريبة", "المجموع الفرعي", "المبلغ الخاضع للضريبة"],
    "tax_total": ["vat", "tax", "tax total", "tax amount", "ضريبة القيمة المضافة", "الضريبة"],
    "total": ["total", "grand total", "total amount", "الإجمالي", "المجموع الكلي", "المبلغ الإجمالي"],
    "discount": ["discount", "الخصم"],
    "shipping": ["shipping", "الشحن"],
    "tip": ["tip", "tips", "الإكرامية"],
    "revenue": ["total revenue", "revenue", "sales", "الإيرادات", "إجمالي الإيرادات", "المبيعات"],
    "cogs": ["cost of goods sold", "cogs", "تكلفة المبيعات"],
    "gross_profit": ["gross profit", "إجمالي الربح", "مجمل الربح"],
    "operating_expenses": ["operating expenses", "المصروفات التشغيلية"],
    "operating_income_ebit": ["operating income", "ebit", "الربح التشغيلي", "الدخل التشغيلي"],
    "net_income": ["net income", "net profit", "صافي الربح", "صافي الدخل"],
    "total_assets": ["total assets", "إجمالي الأصول", "مجموع الموجودات"],
    "total_liabilities": ["total liabilities", "إجمالي الخصوم", "مجموع المطلوبات"],
    "equity": ["equity", "total equity", "shareholders equity", "shareholders' equity", "shareholder's equity", "إجمالي حقوق الملكية", "حقوق المساهمين"],
}


def extract_financial_fields(text: str) -> dict:
    normalized = normalize_digits(text)
    fields: dict[str, Any] = {key: None for key in LABELS}
    for key, labels in LABELS.items():
        labels_pattern = "|".join(re.escape(label) for label in sorted(labels, key=len, reverse=True))
        pattern = rf"^\s*(?:{labels_pattern})(?:\s+\(?\d+(?:\.\d+)?\s*%\)?)?\s*[:=]?\s+(.+?)\s*$"
        matches = re.findall(pattern, normalized, re.I | re.M)
        numbers = [decimal_value(match) for match in matches]
        numbers = [value for value in numbers if value is not None]
        # Multiple periods/columns require model extraction; do not select an arbitrary year.
        if numbers and len(set(numbers)) == 1:
            fields[key] = numbers[0]
    fields["currency"] = detect_currency(text)
    for key, label in [
        ("invoice_date", r"issue\s+date|invoice\s+date|تاريخ\s+الإصدار"),
        ("due_date", r"due\s+date|تاريخ\s+الاستحقاق"),
    ]:
        match = re.search(rf"(?:{label})\s*:?\s*(\d{{1,4}}[-/]\d{{1,2}}[-/]\d{{1,4}})", normalized, re.I)
        fields[key] = match.group(1) if match else None
    rate = re.search(r"(?:VAT|tax|ضريبة)[^\n\d]{0,40}(\d+(?:\.\d+)?)\s*%", normalized, re.I)
    fields["tax_rate"] = Decimal(rate.group(1)) / 100 if rate else None
    return fields


def financial_checks(data: dict, options: FinancialOptions | None = None) -> dict:
    options = options or FinancialOptions()
    quantum = Decimal(1).scaleb(-options.decimal_places)
    checks = []

    def check(name, expected, actual):
        if expected is None or actual is None:
            checks.append({"check": name, "status": "not_checked", "reason": "missing_or_ambiguous_inputs"})
            return
        expected = expected.quantize(quantum, rounding=ROUND_HALF_UP)
        difference = actual - expected
        checks.append(
            {
                "check": name,
                "status": "passed" if abs(difference) <= options.tolerance else "failed",
                "expected": json_number(expected),
                "actual": json_number(actual),
                "difference": json_number(difference),
                "tolerance": str(options.tolerance),
            }
        )

    sub, tax, total = (decimal_value(data.get(key)) for key in ("subtotal", "tax_total", "total"))
    optional = [decimal_value(data.get(key)) for key in ("discount", "shipping", "tip")]
    discount, shipping, tip = (value if value is not None else Decimal(0) for value in optional)
    # Discount is document-level and subtotal is before discount. State this convention in the API guide.
    base = sub - discount if sub is not None else None
    expected = (
        (base + shipping + tip + (Decimal(0) if options.tax_inclusive else tax))
        if base is not None and (tax is not None or options.tax_inclusive)
        else None
    )
    check("document_total", expected, total)
    items = data.get("line_items")
    if isinstance(items, list) and items:
        amounts = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            quantity, price, amount = (decimal_value(item.get(key)) for key in ("quantity", "unit_price", "amount"))
            line_discount = decimal_value(item.get("discount")) or Decimal(0)
            expected_line = quantity * price - line_discount if quantity is not None and price is not None else None
            check(f"line_items.{index}.amount", expected_line, amount)
            amounts.append(amount)
        line_sum = sum(amounts, Decimal(0)) if amounts and all(value is not None for value in amounts) else None
        check("line_items_subtotal", line_sum, sub)
    rate = options.tax_rate if options.tax_rate is not None else decimal_value(data.get("tax_rate"))
    if rate is not None and not Decimal(0) <= rate <= Decimal(1):
        checks.append({"check": "tax", "status": "not_checked", "reason": "tax_rate_must_be_fraction"})
    elif rate is None:
        checks.append({"check": "tax", "status": "not_checked", "reason": "tax_rate_not_provided"})
    else:
        expected_tax = (
            (base * rate / (1 + rate) if options.tax_inclusive else base * rate) if base is not None else None
        )
        check("tax", expected_tax, tax)
    normalized_dates = {}
    for key in ("invoice_date", "due_date"):
        normalized_dates[key] = normalize_date(data.get(key), options.date_order)
    issue, due = (normalized_dates[key][0] for key in ("invoice_date", "due_date"))
    checks.append(
        {
            "check": "date_order",
            "status": "not_checked" if not issue or not due else "passed" if due >= issue else "failed",
            "issueDate": issue,
            "dueDate": due,
            "reason": None if issue and due else "missing_or_ambiguous_dates",
        }
    )
    failed = [entry for entry in checks if entry["status"] == "failed"]
    evaluated = [entry for entry in checks if entry["status"] != "not_checked"]
    return {"status": "needs_review" if failed else "passed" if evaluated else "insufficient_data", "checks": checks}


def financial_ratios(metrics: dict) -> dict:
    values = {key: decimal_value(value) for key, value in metrics.items()}
    result = {}
    for name, numerator, denominator, multiplier in [
        ("gross_margin_pct", "gross_profit", "revenue", 100),
        ("net_profit_margin_pct", "net_income", "revenue", 100),
        ("debt_to_assets_ratio", "total_liabilities", "total_assets", 1),
        ("debt_to_equity_ratio", "total_liabilities", "equity", 1),
    ]:
        top, bottom = values.get(numerator), values.get(denominator)
        result[name] = {
            "value": json_number((top / bottom * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if top is not None and bottom is not None and bottom != 0
            else None,
            "inputs": [numerator, denominator],
            "reason": None
            if top is not None and bottom is not None and bottom != 0
            else "missing_inputs_or_zero_denominator",
        }
    return result


def audit_text(text: str, tax_rate=None, date_order=None, tolerance="0.01") -> dict:
    data = extract_financial_fields(text)
    options = FinancialOptions(tax_rate=tax_rate, date_order=date_order, tolerance=tolerance)
    result = financial_checks(data, options)
    anomalies = [
        {
            "category": "DATE_INVERSION / تناقض التواريخ"
            if row["check"] == "date_order"
            else "ARITHMETIC_ERROR / خطأ حسابي",
            "severity": "CRITICAL / حرج" if row["check"] == "date_order" else "HIGH / مرتفع",
            "check": row["check"],
            "description_en": f"Check {row['check']} failed.",
            "description_ar": f"تحتاج نتيجة {row['check']} إلى مراجعة.",
            **row,
        }
        for row in result["checks"]
        if row["status"] == "failed"
    ]
    return {
        "risk_rating": "CRITICAL_RISK / مخاطر حرجة"
        if any(row["check"] == "date_order" for row in anomalies)
        else "HIGH_RISK / مخاطر عالية"
        if anomalies
        else "CLEAN / سليم"
        if result["status"] == "passed"
        else "UNDETERMINED / غير محدد",
        "is_clean": not anomalies and result["status"] == "passed",
        "total_anomalies": len(anomalies),
        "anomalies": anomalies,
        "checks": result["checks"],
        "status": result["status"],
    }
