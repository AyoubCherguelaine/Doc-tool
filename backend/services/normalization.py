"""Conservative Arabic/English normalization; never infer a missing currency/date."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_digits(value: str) -> str:
    return value.translate(DIGITS).replace("\u066b", ".").replace("\u066c", ",").replace("−", "-").replace("٪", "%")


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", normalize_digits(value)).casefold()
    value = re.sub(r"[\u064b-\u065f\u0670\u0640\u200e\u200f\u061c]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def decimal_value(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    raw = normalize_digits(str(value)).strip()
    negative = raw.startswith("(") and raw.endswith(")")
    if negative:
        raw = raw[1:-1].strip()
    # Strip known currency labels only. Reject other text rather than collecting unrelated digits.
    raw = re.sub(
        r"(?:USD|SAR|AED|EGP|EUR|GBP|DZD|ر\.س|د\.إ|دج|ريال|درهم|جنيه|دينار|[$€£])", "", raw, flags=re.I
    ).strip()
    raw = raw.replace("\u00a0", " ")
    if re.fullmatch(r"[+-]?\d{1,3}(?:[ ,]\d{3})+(?:\.\d+)?", raw):
        raw = raw.replace(",", "").replace(" ", "")
    elif not re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)", raw):
        return None  # e.g. '1,25' needs explicit locale; do not silently interpret as 125.
    try:
        number = Decimal(raw)
        return (-number if negative else number) if number.is_finite() else None
    except InvalidOperation:
        return None


def normalize_date(value: Any, order: str | None = None) -> tuple[str | None, str | None]:
    if value is None:
        return None, "not_provided"
    raw = normalize_digits(str(value)).strip()
    parts = re.fullmatch(r"(\d{1,4})[-/](\d{1,2})[-/](\d{1,4})", raw)
    if not parts:
        return None, "unsupported_date_format"
    a, b, c = (int(part) for part in parts.groups())
    if len(parts.group(1)) == 4:
        year, month, day = a, b, c
    elif len(parts.group(3)) == 4:
        year = c
        if a <= 12 and b <= 12 and a != b and not order:
            return None, "ambiguous_date_order"
        if order == "MDY" or (not order and b > 12):
            month, day = a, b
        else:
            day, month = a, b
    else:
        return None, "four_digit_year_required"
    try:
        return date(year, month, day).isoformat(), None
    except ValueError:
        return None, "invalid_date"


def detect_currency(text: str) -> str | None:
    patterns = {
        "SAR": r"\bSAR\b|ر\.س|ريال\s*سعودي",
        "AED": r"\bAED\b|د\.إ|درهم\s*إماراتي",
        "DZD": r"\bDZD\b|دج|دينار\s*جزائري",
        "EGP": r"\bEGP\b|جنيه\s*مصري",
        "EUR": r"\bEUR\b|€|يورو",
        "USD": r"\bUSD\b|\$|دولار\s*أمريكي",
        "GBP": r"\bGBP\b|£",
    }
    found = [code for code, pattern in patterns.items() if re.search(pattern, text, re.I)]
    return found[0] if len(found) == 1 else None


def json_number(value: Decimal) -> int | float:
    # Calculations stay Decimal. JSON conversion happens only at the response boundary.
    return int(value) if value == value.to_integral() else float(value)
