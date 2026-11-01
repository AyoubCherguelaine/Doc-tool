"""Deterministic, bounded document checks; no eval or user-provided executable code."""

from __future__ import annotations

from backend.services.models import DocumentRule
from backend.services.normalization import decimal_value, normalize_text


def read_field(data, path: str):
    current = data
    for key in path.split("."):
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and key.isdigit() and int(key) < len(current):
            current = current[int(key)]
        else:
            return None
    return current


def evaluate_rules(data: dict, rules: list[DocumentRule]) -> dict:
    results = []
    for rule in rules:
        actual = read_field(data, rule.field)
        if rule.operator == "required":
            passed = actual is not None and actual != "" and actual != [] and actual != {}
        elif actual is None:
            passed = False
        elif rule.operator in {"gte", "lte"}:
            left, right = decimal_value(actual), decimal_value(rule.value)
            passed = (
                left is not None and right is not None and (left >= right if rule.operator == "gte" else left <= right)
            )
        elif rule.operator == "eq":
            passed = actual == rule.value
        elif rule.operator == "neq":
            passed = actual != rule.value
        elif rule.operator == "in":
            passed = actual in rule.value
        else:
            passed = isinstance(actual, str) and normalize_text(rule.value) in normalize_text(actual)
        results.append(
            {
                "field": rule.field,
                "operator": rule.operator,
                "expected": rule.value,
                "actual": actual,
                "status": "passed" if passed else "failed",
                "severity": rule.severity,
                "message": rule.message,
                "reason": "not_provided" if actual is None else None,
            }
        )
    return {
        "status": "rejected"
        if any(row["status"] == "failed" and row["severity"] == "error" for row in results)
        else "needs_review"
        if any(row["status"] == "failed" for row in results)
        else "passed",
        "checks": results,
    }
