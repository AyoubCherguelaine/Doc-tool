"""
Bilingual (English & Arabic) Intelligence Tools for Enterprise Document Processing.

Provides deterministic regex and rule engines for:
- Redaction & PII anonymization (Saudi National ID, Iqama, GCC IBAN, VAT/TIN, CR, phone, email)
- Fast document categorization & language detection (EN / AR)
- Financial statement metric extraction & ratio calculation
- Arithmetic, configurable tax, and date anomaly auditing
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


class BilingualDocumentKit:
    """Enterprise bilingual processing toolkit for Arabic and English documents."""

    # -----------------------------------------------------------------------
    # 1. Bilingual Redaction & PII Anonymization
    # -----------------------------------------------------------------------

    @staticmethod
    def redact_pii(text: str) -> Dict[str, Any]:
        """
        Redact sensitive PII in English and Arabic text.
        Masks National IDs, Iqama, IBANs, Credit Cards, Tax Numbers, Phones, and Emails.
        """
        findings: List[Dict[str, Any]] = []
        redacted = text

        patterns = [
            # Saudi / Gulf IBANs (e.g. SA0380000000608010167519, AE070331234567890123456, EG...)
            (
                r"\b(SA\d{2}[0-9A-Z]{20}|AE\d{21}|EG\d{27}|[A-Z]{2}\d{2}[0-9A-Z]{12,30})\b",
                "[REDACTED_IBAN / آيبان_محجوب]",
                "IBAN / الحساب البنكي الدولي",
            ),
            # Saudi Tax ID (ZATCA 15 digits starting and ending with 3: 3xxxxxxxxxxxx3)
            (
                r"\b(3\d{13}3)\b",
                "[REDACTED_TAX_ID / رقم_ضريبي_محجوب]",
                "Tax Identification Number / الرقم الضريبي",
            ),
            # Saudi National ID / Iqama (10 digits starting with 1 or 2)
            (
                r"\b([12]\d{9})\b",
                "[REDACTED_NATIONAL_ID / هوية_وطنية_أو_إقامة_محجوبة]",
                "National ID or Iqama / هوية وطنية أو إقامة",
            ),
            # US SSN (xxx-xx-xxxx)
            (
                r"\b(\d{3}-\d{2}-\d{4})\b",
                "[REDACTED_SSN / رقم_تأمين_محجوب]",
                "Social Security Number (SSN)",
            ),
            # Credit Card Numbers (13 to 19 digits with optional dashes/spaces)
            (
                r"\b(?:\d{4}[ -]?){3}\d{4}\b",
                "[REDACTED_CREDIT_CARD / بطاقة_ائتمان_محجوبة]",
                "Credit Card / بطاقة بنكية",
            ),
            # Email addresses
            (
                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
                "[REDACTED_EMAIL / بريد_محجوب]",
                "Email Address / البريد الإلكتروني",
            ),
            # Saudi / Gulf Phone numbers (+966, 05x, +971, +20, etc.)
            (
                r"(?:\+966|00966|966)?0?5\d{8}\b|\+971\d{8,9}\b|\+20\d{10}\b|\+?1?\d{3}[-.\s]\d{3}[-.\s]\d{4}\b",
                "[REDACTED_PHONE / هاتف_محجوب]",
                "Phone Number / رقم الهاتف",
            ),
            # Commercial Registration (CR / سجل تجاري: 10 digits starting with 10, 20, 40, etc.)
            (
                r"(?:سجل\s*تجاري|CR|C\.R\.|س\.ت)[:\s#]*(\d{10})\b",
                "سجل تجاري: [REDACTED_CR / سجل_محجوب]",
                "Commercial Registration / السجل التجاري",
            ),
        ]

        for regex, mask, label in patterns:
            for match in re.finditer(regex, redacted, flags=re.IGNORECASE):
                val = match.group(0)
                findings.append(
                    {
                        "type": label,
                        "masked": mask,
                        "original_snippet": val[:3] + "•••" + val[-2:] if len(val) > 5 else "•••",
                    }
                )
            redacted = re.sub(regex, mask, redacted, flags=re.IGNORECASE)

        return {
            "redacted_text": redacted,
            "total_redactions": len(findings),
            "findings": findings,
            "status": "sanitized",
        }

    # -----------------------------------------------------------------------
    # 2. Bilingual Document Classification & Routing
    # -----------------------------------------------------------------------

    @staticmethod
    def classify_document(text: str) -> Dict[str, Any]:
        """
        Classify document category, language, and routing department in English and Arabic.
        """
        # 1. Detect language distribution
        arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
        latin_chars = len(re.findall(r"[A-Za-z]", text))
        total_letters = arabic_chars + latin_chars or 1

        if arabic_chars / total_letters > 0.6:
            primary_lang = "ar"
            lang_label = "Arabic / العربية"
        elif latin_chars / total_letters > 0.6:
            primary_lang = "en"
            lang_label = "English / الإنجليزية"
        else:
            primary_lang = "mixed"
            lang_label = "Bilingual / مزدوج اللغة (AR & EN)"

        lower = text.lower()

        # Category profiles
        categories = {
            "INVOICE": {
                "name_en": "Tax Invoice / Billing",
                "name_ar": "فاتورة ضريبية / مطالبة مالية",
                "department": "Finance & Accounts Payable / المالية والمحاسبة",
                "keywords": [
                    "invoice",
                    "tax invoice",
                    "bill to",
                    "subtotal",
                    "vat",
                    "due date",
                    "فاتورة",
                    "فاتورة ضريبية",
                    "الرقم الضريبي",
                    "المجموع",
                    "ضريبة القيمة المضافة",
                    "تاريخ الاستحقاق",
                    "المورد",
                    "العميل",
                ],
            },
            "CONTRACT": {
                "name_en": "Legal Contract / Agreement",
                "name_ar": "عقد قانوني / اتفاقية ملزمة",
                "department": "Legal & Compliance / الشؤون القانونية",
                "keywords": [
                    "agreement",
                    "contract",
                    "parties",
                    "indemnification",
                    "jurisdiction",
                    "termination",
                    "hereby",
                    "عقد",
                    "اتفاقية",
                    "الطرف الأول",
                    "الطرف الثاني",
                    "البند",
                    "المادة",
                    "التعويض",
                    "القانون الحاكم",
                    "فسخ العقد",
                    "الاختصاص القضائي",
                ],
            },
            "FINANCIAL_STATEMENT": {
                "name_en": "Financial Statement / P&L",
                "name_ar": "قوائم مالية / ميزانية وأرباح وخسائر",
                "department": "Corporate Finance & Audit / المالية وإدارة التدقيق",
                "keywords": [
                    "balance sheet",
                    "income statement",
                    "cash flow",
                    "ebitda",
                    "net income",
                    "gross profit",
                    "assets",
                    "الميزانية العمومية",
                    "قائمة الدخل",
                    "التدفقات النقدية",
                    "الأصول",
                    "الخصوم",
                    "صافي الربح",
                    "إجمالي الإيرادات",
                ],
            },
            "RESUME": {
                "name_en": "Resume / CV",
                "name_ar": "سيرة ذاتية / ملف ترشيح",
                "department": "Human Resources & Talent Acquisition / الموارد البشرية",
                "keywords": [
                    "resume",
                    "curriculum vitae",
                    "education",
                    "work experience",
                    "skills",
                    "bachelor",
                    "master",
                    "سيرة ذاتية",
                    "الخبرات المهنية",
                    "المؤهلات العلمية",
                    "المهارات",
                    "التعليم",
                    "جامعة",
                    "بكالوريوس",
                ],
            },
            "COMMERCIAL_REGISTRATION": {
                "name_en": "Commercial Registration (CR)",
                "name_ar": "شهادة سجل تجاري أو ترخيص",
                "department": "Corporate Affairs & Governance / شؤون الشركات والترخيص",
                "keywords": [
                    "commercial registration",
                    "ministry of commerce",
                    "cr number",
                    "license",
                    "سجل تجاري",
                    "وزارة التجارة",
                    "رقم السجل",
                    "الاسم التجاري",
                    "الكيان القانوني",
                    "رأس المال",
                ],
            },
            "OFFICIAL_LETTER": {
                "name_en": "Official Letter / Government Circular",
                "name_ar": "خطاب رسمي / تعميم إداري",
                "department": "Executive Management / الإدارة التنفيذية",
                "keywords": [
                    "circular",
                    "memorandum",
                    "subject:",
                    "dear sir",
                    "respectfully",
                    "تعميم",
                    "خطاب",
                    "سعادة",
                    "المحترمين",
                    "السلام عليكم",
                    "الموضوع",
                    "إشارة إلى",
                    "وتقبلوا خالص التحية",
                ],
            },
        }

        best_category = "GENERAL_DOCUMENT"
        best_score = 0
        best_info = {
            "name_en": "General Document",
            "name_ar": "مستند عام",
            "department": "Operations / العمليات",
        }

        for cat_id, info in categories.items():
            matches = sum(1 for kw in info["keywords"] if kw in lower)
            if matches > best_score:
                best_score = matches
                best_category = cat_id
                best_info = info

        confidence = min(0.99, max(0.40, best_score / 6.0))

        return {
            "category": best_category,
            "category_name_en": best_info["name_en"],
            "category_name_ar": best_info["name_ar"],
            "primary_language": primary_lang,
            "language_label": lang_label,
            "confidence": round(confidence, 2),
            "routing_department": best_info["department"],
            "priority": "URGENT / عاجل"
            if any(w in lower for w in ["urgent", "عاجل", "immediate", "فوري"])
            else "NORMAL / عادي",
        }

    # -----------------------------------------------------------------------
    # 3. Bilingual Financial Statement Analysis
    # -----------------------------------------------------------------------

    @staticmethod
    def analyze_financial_statement(text: str) -> Dict[str, Any]:
        """Read explicit financial values without assuming currency or suppressing zero values."""
        from backend.services.finance import extract_financial_fields, financial_ratios
        from backend.services.normalization import json_number

        fields = extract_financial_fields(text)
        keys = [
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
        metrics = {key: fields.get(key) for key in keys}
        ratios = financial_ratios(metrics)
        return {
            "currency": fields["currency"],
            "metrics": {key: json_number(value) if value is not None else None for key, value in metrics.items()},
            "financial_ratios": {key: row["value"] for key, row in ratios.items()},
            "ratio_details": ratios,
            "summary_en": "Extracted reported financial figures.",
            "summary_ar": "المؤشرات المالية الواردة في المستند.",
        }

    @staticmethod
    def audit_anomalies(text: str, tax_rate=None, date_order=None, tolerance="0.01") -> Dict[str, Any]:
        """Use decimal arithmetic and explicit tax/date configuration; unknown is not clean."""
        from backend.services.finance import audit_text

        return audit_text(text, tax_rate=tax_rate, date_order=date_order, tolerance=tolerance)
