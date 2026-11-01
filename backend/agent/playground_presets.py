"""
Playground Presets and Sample Contexts for DOCTool Document AI Services.

Provides service-specific default system prompts, schema templates,
user queries, and realistic sample document contexts for each service.
"""

from typing import Any, Dict

from backend.config import settings

SERVICE_PRESETS: Dict[str, Dict[str, Any]] = {
    "invoice": {
        "id": "invoice",
        "name": "Invoice Processing",
        "category": "finance",
        "description": "Extract structured invoice data — line items, totals, taxes — as verified JSON.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.1,
        "default_system_prompt": (
            "You are an expert invoice processing agent. Your primary objective is to extract complete structured invoice "
            "data and return ONLY a valid JSON object matching the requested schema.\n"
            "Execution Instructions:\n"
            "1. Extract invoice number, dates, vendor, client, line items, subtotal, tax rate, tax amount, and total.\n"
            "2. Verify arithmetic: subtotal + tax = total.\n"
            "3. Output clean, valid JSON only without markdown explanation or code fence."
        ),
        "default_query": "Extract all invoice line items, vendor details, client info, taxes, and total amounts.",
        "default_schema": {
            "invoice_number": "INV-2026-0042",
            "issue_date": "2026-10-15",
            "due_date": "2026-10-31",
            "currency": "USD",
            "vendor": {
                "name": "CloudScale Solutions LLC",
                "tax_id": "US-987654321",
                "email": "billing@cloudscale.io",
                "address": "100 Tech Boulevard, Suite 400, San Francisco, CA 94107",
            },
            "client": {
                "name": "Acme Global Enterprise",
                "tax_id": "US-123456789",
                "email": "procurement@acme.com",
                "address": "500 Market St, Denver, CO 80202",
            },
            "line_items": [
                {
                    "description": "Enterprise Cloud Hosting - Tier 3",
                    "quantity": 1,
                    "unit_price": 2500.0,
                    "amount": 2500.0,
                },
                {
                    "description": "AI Agent Runtime Add-on (100k queries)",
                    "quantity": 2,
                    "unit_price": 450.0,
                    "amount": 900.0,
                },
            ],
            "subtotal": 3400.0,
            "tax_rate": 0.1,
            "tax_amount": 340.0,
            "total_amount": 3740.0,
            "payment_terms": "Net 15 via Wire Transfer to IBAN US89CSCL1234567890",
        },
        "sample_text": (
            "INVOICE\n"
            "Invoice Number: INV-2026-0042\n"
            "Invoice Date: October 15, 2026\n"
            "Payment Due: October 31, 2026\n"
            "Currency: USD\n\n"
            "VENDOR:\n"
            "CloudScale Solutions LLC\n"
            "Tax ID / EIN: US-987654321\n"
            "100 Tech Boulevard, Suite 400, San Francisco, CA 94107\n"
            "Email: billing@cloudscale.io | Phone: +1 (415) 555-0199\n\n"
            "BILLED TO:\n"
            "Acme Global Enterprise\n"
            "Client Tax ID: US-123456789\n"
            "500 Market St, Denver, CO 80202\n"
            "Attention: Accounts Payable (procurement@acme.com)\n\n"
            "LINE ITEMS:\n"
            "| Item Description | Qty | Unit Price | Total Amount |\n"
            "| Enterprise Cloud Hosting - Tier 3 | 1 | $2,500.00 | $2,500.00 |\n"
            "| AI Agent Runtime Add-on (100k queries) | 2 | $450.00 | $900.00 |\n"
            "| Dedicated Technical Account Manager (Q4) | 1 | $1,200.00 | $1,200.00 |\n\n"
            "FINANCIAL TOTALS:\n"
            "Subtotal: $4,600.00\n"
            "State & Local Tax (8.5%): $391.00\n"
            "Total Amount Due: $4,991.00\n\n"
            "PAYMENT TERMS:\n"
            "Net 15 days. Please remit wire transfer to Silicon Valley Bank, Routing #121000358, Account #9876543210.\n"
            "Thank you for your business!"
        ),
    },
    "receipt": {
        "id": "receipt",
        "name": "Receipt & Expenses",
        "category": "finance",
        "description": "Itemized receipts, tax breakdowns, tips, and financial math verification.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.1,
        "default_system_prompt": (
            "You are a receipt processing and expense categorization specialist. Extract merchant details, date, time, "
            "line items, taxes, tips, and total amount. Return ONLY valid JSON matching the requested schema."
        ),
        "default_query": "Extract merchant details, purchased items, taxes, payment card, and total expense.",
        "default_schema": {
            "merchant": {
                "name": "Blue Bottle Coffee",
                "address": "66 Mint Plaza, San Francisco, CA",
                "phone": "+1 415-555-2345",
            },
            "date": "2026-10-22",
            "time": "08:42 AM",
            "items": [
                {"name": "Hayes Valley Espresso", "quantity": 1, "price": 4.5},
                {"name": "Almond Croissant", "quantity": 1, "price": 5.25},
            ],
            "subtotal": 9.75,
            "tax": 0.83,
            "tip": 2.0,
            "total": 12.58,
            "payment_method": "Visa ending in 4242",
            "expense_category": "Meals & Entertainment",
        },
        "sample_text": (
            "BLUE BOTTLE COFFEE\n"
            "Store #104 - 66 Mint Plaza\n"
            "San Francisco, CA 94103\n"
            "Tel: (415) 555-2345\n\n"
            "Date: 10/22/2026  Time: 08:42:15 AM\n"
            "Order # 38291\n"
            "Server: Elena\n\n"
            "1x Hayes Valley Espresso       $4.50\n"
            "1x Almond Croissant            $5.25\n"
            "1x Sparking Water (12oz)       $3.00\n\n"
            "Subtotal:                     $12.75\n"
            "Tax (8.5%):                    $1.08\n"
            "Tip:                           $2.50\n"
            "TOTAL:                        $16.33\n\n"
            "Payment Method: VISA CONTACTLESS\n"
            "Card: ************4242  Auth: 098172\n"
            "Category: Meals / Travel Expense"
        ),
    },
    "contract": {
        "id": "contract",
        "name": "Contract Analysis",
        "category": "legal",
        "description": "Identify parties, clauses, obligations, renewal terms, and flag legal risks.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.1,
        "default_system_prompt": (
            "You are an enterprise contract intelligence and legal analysis agent. Extract parties, effective dates, "
            "governing law, key clauses (termination, liability, indemnification), and evaluate risk flags. "
            "Return ONLY valid JSON matching the requested schema."
        ),
        "default_query": "Analyze this contract: extract parties, term, termination clauses, liability limits, and potential risks.",
        "default_schema": {
            "title": "Master Software As A Service Agreement",
            "parties": [
                {"name": "DataVault Inc.", "role": "Provider", "jurisdiction": "Delaware"},
                {"name": "Horizon Retailers Ltd.", "role": "Customer", "jurisdiction": "California"},
            ],
            "effective_date": "2026-11-01",
            "term_months": 24,
            "auto_renew": True,
            "renewal_notice_period_days": 60,
            "governing_law": "State of New York",
            "liability_cap": "12 months of fees paid prior to the incident",
            "key_clauses": {
                "confidentiality_duration": "5 years following termination",
                "data_protection": "GDPR and CCPA compliant with 48h breach notification",
                "termination_for_convenience": "90 days written notice",
            },
            "risk_flags": [
                {
                    "severity": "medium",
                    "clause": "Automatic 24-month renewal",
                    "recommendation": "Negotiate 12-month auto-renewal with 30-day notice window.",
                }
            ],
            "overall_risk_score_1_to_10": 3.5,
        },
        "sample_text": (
            "MASTER SOFTWARE AS A SERVICE AGREEMENT\n\n"
            "This Master Software as a Service Agreement ('Agreement') is entered into as of November 1, 2026 ('Effective Date')\n"
            "by and between DataVault Inc., a Delaware corporation with offices at 200 Park Avenue, New York, NY ('Provider'),\n"
            "and Horizon Retailers Ltd., a California corporation located at 742 Evergreen Terrace, San Jose, CA ('Customer').\n\n"
            "1. TERM AND RENEWAL\n"
            "The initial term of this Agreement shall be twenty-four (24) months from the Effective Date. This Agreement\n"
            "shall automatically renew for successive twenty-four (24) month terms unless either party provides written\n"
            "notice of non-renewal at least sixty (60) days prior to the expiration of the then-current term.\n\n"
            "2. LIMITATION OF LIABILITY\n"
            "EXCEPT FOR BREACHES OF CONFIDENTIALITY OR INDEMNIFICATION OBLIGATIONS, NEITHER PARTY'S AGGREGATE LIABILITY\n"
            "UNDER THIS AGREEMENT SHALL EXCEED THE TOTAL FEES ACTUALLY PAID BY CUSTOMER TO PROVIDER IN THE TWELVE (12)\n"
            "MONTHS PRECEDING THE CLAIM.\n\n"
            "3. TERMINATION FOR CONVENIENCE\n"
            "Customer may terminate this Agreement without cause upon ninety (90) days prior written notice, subject to\n"
            "payment of an early termination fee equal to 50% of the remaining contract value.\n\n"
            "4. GOVERNING LAW\n"
            "This Agreement shall be governed by and construed in accordance with the laws of the State of New York,\n"
            "without regard to conflict of law principles."
        ),
    },
    "compliance": {
        "id": "compliance",
        "name": "PII & Compliance Audit",
        "category": "legal",
        "description": "Detect sensitive PII, GDPR/HIPAA risks, and secret leaks with risk scores.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.0,
        "default_system_prompt": (
            "You are a compliance and data privacy auditor. Scan documents for PII (names, emails, phones, SSNs, "
            "credit cards, health data, national IDs), identify GDPR/HIPAA exposure, compute a risk score (0-100), "
            "and provide remediation steps. Return ONLY valid JSON."
        ),
        "default_query": "Audit this document for PII, GDPR compliance violations, and security leaks.",
        "default_schema": {
            "compliance_status": "HIGH_RISK",
            "overall_risk_score": 85,
            "summary": "Document contains unmasked Social Security Numbers and patient health diagnoses.",
            "detected_pii": [
                {"type": "SSN", "value_masked": "***-**-6789", "risk": "CRITICAL", "count": 2},
                {"type": "Health Condition", "value_masked": "[DIAGNOSIS_REDACTED]", "risk": "HIGH", "count": 1},
                {"type": "Email Address", "value_masked": "j***@patientcare.org", "risk": "MEDIUM", "count": 3},
            ],
            "regulations_impacted": ["HIPAA Security Rule 45 CFR", "GDPR Article 9 (Special Category Data)"],
            "remediation_actions": [
                "Redact SSN and medical records before transmitting to external vendors.",
                "Enforce end-to-end encryption for stored patient intake forms.",
            ],
        },
        "sample_text": (
            "CONFIDENTIAL PATIENT INTAKE RECORD - MEMORIAL HOSPITAL\n"
            "Date: 2026-10-18 | Provider: Dr. Sarah Jenkins, MD\n\n"
            "PATIENT PROFILE:\n"
            "Name: Jonathan Robert Miller\n"
            "DOB: 1984-06-12\n"
            "Social Security Number: 456-78-6789\n"
            "Email: jmiller@patientcare.org | Phone: (555) 234-8901\n"
            "Residential Address: 14 Maple Street, Cambridge, MA 02138\n\n"
            "CLINICAL NOTES:\n"
            "Patient presented with chronic hypertension and Stage 2 Cardiac Arrhythmia. Currently prescribed\n"
            "Lisinopril 20mg daily. Family history indicates cardiovascular predispositions.\n\n"
            "INSURANCE DETAILS:\n"
            "Carrier: Blue Cross Blue Shield\n"
            "Policy Number: BCBS-992014-X\n"
            "Group ID: G-4821"
        ),
    },
    "form_parser": {
        "id": "form_parser",
        "name": "Intelligent Form Parser",
        "category": "extraction",
        "description": "Extract form key-values, checkbox states, selection groups, and signatures.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.1,
        "default_system_prompt": (
            "You are an intelligent form parser. Extract key-value field pairs, determine checkbox states (checked/unchecked), "
            "and identify signatory presence. Return ONLY valid JSON matching the requested schema."
        ),
        "default_query": "Parse this form: extract all fields, checkboxes ([X] vs [ ]), and signatory status.",
        "default_schema": {
            "form_name": "Employee Onboarding & Direct Deposit Authorization",
            "form_id": "HR-DD-2026",
            "fields": {
                "employee_full_name": "Maya Lin Rodriguez",
                "employee_id": "EMP-8841",
                "bank_name": "Chase Bank N.A.",
                "account_type": "Checking",
                "routing_number": "021000021",
                "account_number_last4": "5512",
            },
            "checkboxes": {
                "agree_to_electronic_delivery": True,
                "opt_in_401k_matching": True,
                "parking_permit_requested": False,
            },
            "signature": {"is_signed": True, "signed_by": "Maya Lin Rodriguez", "date_signed": "2026-10-24"},
        },
        "sample_text": (
            "FORM HR-DD-2026: DIRECT DEPOSIT & BENEFIT AUTHORIZATION\n\n"
            "1. EMPLOYEE INFORMATION:\n"
            "Full Legal Name: Maya Lin Rodriguez\n"
            "Employee ID: EMP-8841\n"
            "Department: Cloud Engineering\n"
            "Start Date: 2026-11-01\n\n"
            "2. BANKING DETAILS:\n"
            "Financial Institution: Chase Bank N.A.\n"
            "Account Type: [X] Checking  [ ] Savings\n"
            "Routing Transit Number: 021000021\n"
            "Account Number: *******5512\n\n"
            "3. PREFERENCES & ELECTIONS:\n"
            "[X] I authorize direct deposit of my payroll earnings.\n"
            "[X] Automatically enroll in company 401(k) 4% match program.\n"
            "[ ] Request monthly downtown transit parking subsidy.\n\n"
            "SIGNATURE:\n"
            "Signature: /s/ Maya Lin Rodriguez (Electronic Timestamp: 2026-10-24T14:22:00Z)\n"
            "Date Signed: October 24, 2026"
        ),
    },
    "resume": {
        "id": "resume",
        "name": "Resume & Talent Intelligence",
        "category": "hr",
        "description": "Candidate profiling, skills taxonomy, work history, and seniority assessment.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.1,
        "default_system_prompt": (
            "You are an executive talent evaluator and HR intelligence agent. Extract candidate personal info, "
            "skills taxonomy, work experience timeline, education, and compute an objective seniority score. "
            "Return ONLY valid JSON."
        ),
        "default_query": "Extract candidate skills, experience years, seniority level, and educational background.",
        "default_schema": {
            "candidate": {
                "name": "Alex Mercer",
                "email": "alex.mercer@devmail.io",
                "phone": "+1 415-555-0144",
                "location": "Seattle, WA",
                "github": "github.com/alexmercer-ai",
            },
            "current_title": "Lead AI Platform Engineer",
            "total_experience_years": 8.5,
            "seniority_level": "Staff / Lead",
            "skills": {
                "languages": ["Python", "TypeScript", "Rust", "Go"],
                "ai_frameworks": ["PyTorch", "LangChain", "LlamaIndex", "HuggingFace"],
                "infrastructure": ["Kubernetes", "Docker", "PostgreSQL", "AWS", "Kafka"],
            },
            "experience": [
                {
                    "company": "Cognitive Cloud Inc",
                    "role": "Lead AI Platform Engineer",
                    "duration": "2023 - Present",
                    "highlights": ["Architected distributed RAG serving 5M daily queries with sub-100ms latency."],
                },
                {
                    "company": "Neural Systems LLC",
                    "role": "Senior Backend Engineer",
                    "duration": "2020 - 2023",
                    "highlights": ["Built high-throughput model inference pipelines in Python and FastAPI."],
                },
            ],
            "education": [
                {"degree": "B.S. in Computer Science", "institution": "University of Washington", "year": 2018}
            ],
        },
        "sample_text": (
            "ALEX MERCER\n"
            "Seattle, WA | alex.mercer@devmail.io | +1 (415) 555-0144 | github.com/alexmercer-ai\n\n"
            "PROFESSIONAL SUMMARY:\n"
            "Lead AI Platform Engineer with 8.5 years of experience architecting large-scale distributed systems,\n"
            "vector search retrieval pipelines, and enterprise LLM agents.\n\n"
            "WORK EXPERIENCE:\n"
            "Lead AI Platform Engineer | Cognitive Cloud Inc (2023 - Present)\n"
            "- Designed and implemented multi-tenant RAG search serving 5,000,000 requests per day.\n"
            "- Cut vector retrieval p99 latency from 340ms to 85ms via hybrid FAISS + BM25 indexing.\n"
            "- Managed an engineering squad of 6 senior backend and ML engineers.\n\n"
            "Senior Backend Engineer | Neural Systems LLC (2020 - 2023)\n"
            "- Built async Python microservices using FastAPI, Redis, and PostgreSQL.\n"
            "- Automated deployment pipelines using Docker and Kubernetes on AWS EKS.\n\n"
            "TECHNICAL SKILLS:\n"
            "Languages: Python, TypeScript, Rust, Go, SQL\n"
            "AI & ML: PyTorch, LangChain, LlamaIndex, pgvector, HuggingFace Transformers\n"
            "Cloud: AWS (ECS, EKS, RDS), Docker, Kubernetes, Terraform\n\n"
            "EDUCATION:\n"
            "B.S. in Computer Science | University of Washington, 2018 (Magna Cum Laude)"
        ),
    },
    "redaction": {
        "id": "redaction",
        "name": "PII & Tax Redaction (AR / EN)",
        "category": "legal",
        "description": "Mask Saudi National IDs, GCC IBANs, ZATCA Tax IDs, CRs, and sensitive contact info.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.0,
        "default_system_prompt": (
            "You are an expert bilingual redaction agent for Arabic and English enterprise documents. Mask Saudi National IDs "
            "(10 digits), ZATCA 15-digit VAT IDs, GCC IBANs, Commercial Registrations (CR), phones, and emails with standardized "
            "[REDACTED_...] tokens while preserving document context. Return ONLY valid JSON."
        ),
        "default_query": "Identify and redact all Saudi/GCC PII, VAT numbers, CR, IBAN, and contact data.",
        "default_schema": {
            "redacted_text": "شركة الأفق للتجارة - الرقم الضريبي [REDACTED_VAT] وسجل تجاري [REDACTED_CR]...",
            "detected_entities_count": {"saudi_national_id": 1, "vat_id": 1, "iban": 1, "phone": 1, "email": 1},
            "redacted_items": [
                {"type": "VAT_ID", "original_snippet": "300123456789003", "replacement": "[REDACTED_VAT]"},
                {"type": "IBAN", "original_snippet": "SA0380000000608010167519", "replacement": "[REDACTED_IBAN]"},
            ],
        },
        "sample_text": (
            "عقد توريد وخدمات استشارية\n"
            "بين شركة الأفق للتجارة العامة، سجل تجاري رقم: 1010987654، ورقم ضريبي مسجل لدى هيئة الزكاة والضريبة والجمارك (ZATCA): 300123456789003\n"
            "الممثل النظامي: السيد عبد الله الشمري، هوية وطنية رقم: 1087654321، جوال: +966 50 123 4567، بريد إلكتروني: abdullah@alofooq.sa\n"
            "الحساب البنكي لتحويل المستحقات: آيبان SA0380000000608010167519 لدى مصرف الراجحي، فرع الرياض الرئيسي."
        ),
    },
    "classifier": {
        "id": "classifier",
        "name": "Document Classification & Routing",
        "category": "extraction",
        "description": "Categorize documents, detect language (EN/AR), urgency, and target department.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.1,
        "default_system_prompt": (
            "You are an enterprise document triage agent. Classify the document type, primary language, urgency level, "
            "target corporate department, and compute a confidence score. Return ONLY valid JSON."
        ),
        "default_query": "Classify this document: determine document type, language, department routing, and priority.",
        "default_schema": {
            "document_type": "commercial_invoice",
            "primary_language": "ar-SA",
            "bilingual": True,
            "confidence_score": 0.98,
            "target_department": "Accounts Payable / Finance",
            "urgency_level": "HIGH",
            "action_summary": "Invoice due in 5 days; forward to treasury for payment processing.",
        },
        "sample_text": (
            "PASSENGER VEHICLE LEASE AGREEMENT\n"
            "This Agreement is executed between Premier Fleet Management LLC and Apex Logistics Corp.\n"
            "Subject: 15 Commercial Delivery Vans (Model Year 2026)\n"
            "Monthly Lease Payment: $14,500.00 | Effective Period: 36 Months\n"
            "Requires immediate review by Legal & Fleet Operations prior to registration."
        ),
    },
    "financial_statement": {
        "id": "financial_statement",
        "name": "Financial Statement Analysis",
        "category": "finance",
        "description": "Analyze Income Statement and Balance Sheet metrics and calculate key ratios.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.1,
        "default_system_prompt": (
            "You are a CFA-grade corporate financial analyst. Extract income statement and balance sheet line items, "
            "and compute key financial ratios (Gross Margin, Operating Margin, Current Ratio, Debt-to-Equity). "
            "Return ONLY valid JSON."
        ),
        "default_query": "Extract revenue, expenses, net income, assets, liabilities, and calculate key ratios.",
        "default_schema": {
            "reporting_period": "Q3 2026 (Ended September 30, 2026)",
            "currency": "USD",
            "income_statement": {
                "revenue": 12500000.0,
                "cost_of_goods_sold": 4500000.0,
                "gross_profit": 8000000.0,
                "operating_expenses": 5100000.0,
                "operating_income_ebit": 2900000.0,
                "net_income": 2250000.0,
            },
            "balance_sheet": {
                "current_assets": 18200000.0,
                "total_assets": 42000000.0,
                "current_liabilities": 7500000.0,
                "total_liabilities": 16000000.0,
                "total_equity": 26000000.0,
            },
            "financial_ratios": {
                "gross_margin_percent": 64.0,
                "net_profit_margin_percent": 18.0,
                "current_ratio": 2.43,
                "debt_to_equity_ratio": 0.62,
            },
        },
        "sample_text": (
            "APEX TECHNOLOGIES INC. - CONDENSED CONSOLIDATED STATEMENT OF OPERATIONS\n"
            "For the Three Months Ended September 30, 2026 (in USD)\n\n"
            "Revenues: $12,500,000\n"
            "Cost of Revenue: $4,500,000\n"
            "Gross Profit: $8,000,000 (64.0%)\n\n"
            "Operating Expenses:\n"
            "Research & Development: $2,800,000\n"
            "Sales & Marketing: $1,400,000\n"
            "General & Administrative: $900,000\n"
            "Total Operating Expenses: $5,100,000\n\n"
            "Income from Operations (EBIT): $2,900,000\n"
            "Income Tax Expense: $650,000\n"
            "Net Income: $2,250,000\n\n"
            "BALANCE SHEET HIGHLIGHTS:\n"
            "Cash & Cash Equivalents: $11,200,000\n"
            "Current Assets: $18,200,000 | Current Liabilities: $7,500,000\n"
            "Total Assets: $42,000,000 | Total Stockholders' Equity: $26,000,000"
        ),
    },
    "translation": {
        "id": "translation",
        "name": "Bilingual Legal & Financial Translation",
        "category": "general",
        "description": "High-precision translation between Arabic and English preserving terminology.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.1,
        "default_system_prompt": (
            "You are a legal and financial document translator between English and Arabic. Translate the provided document "
            "with precise terminology preservation, maintaining numbers, dates, and tables. Return ONLY valid JSON."
        ),
        "default_query": "Translate this legal/commercial text into Arabic preserving legal phrasing and terms.",
        "default_schema": {
            "source_language": "English",
            "target_language": "Arabic",
            "translated_title": "اتفاقية عدم الإفصاح عن المعلومات وسرية البيانات",
            "translated_content": "تتعهد الأطراف الموقعة أدناه بالحفاظ على سرية كافة البيانات الفنية والتجارية...",
            "preserved_terms": [
                {"english": "Non-Disclosure Agreement (NDA)", "arabic": "اتفاقية عدم الإفصاح"},
                {"english": "Confidential Information", "arabic": "المعلومات السرية"},
                {"english": "Governing Law", "arabic": "القانون الواجب التطبيق"},
            ],
        },
        "sample_text": (
            "NON-DISCLOSURE AND CONFIDENTIALITY AGREEMENT\n"
            "1. Definition of Confidential Information:\n"
            "'Confidential Information' refers to all proprietary data, financial projections, customer lists, algorithms,\n"
            "and software architecture disclosed by the Disclosing Party to the Receiving Party, whether orally or in writing.\n\n"
            "2. Non-Disclosure Obligations:\n"
            "The Receiving Party agrees to protect the Confidential Information using the same degree of care it uses for\n"
            "its own confidential information, but not less than reasonable care, and shall not disclose such information\n"
            "to any third party without prior written authorization."
        ),
    },
    "anomaly_audit": {
        "id": "anomaly_audit",
        "name": "Anomaly & Tax Audit",
        "category": "finance",
        "description": "Check invoice arithmetic, the stated or configured tax rate, and date order.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.0,
        "default_system_prompt": (
            "You are a forensic tax auditor. Validate mathematical integrity: check whether line item quantities * unit prices = amounts, "
            "sum of amounts = subtotal, verify the explicitly stated or configured tax calculation, and check due date chronology. Return ONLY valid JSON."
        ),
        "default_query": "Audit this invoice for mathematical mismatches, VAT errors, and chronological date conflicts.",
        "default_schema": {
            "audit_passed": False,
            "overall_status": "DISCREPANCIES_FOUND",
            "math_check": {
                "subtotal_stated": 10000.0,
                "subtotal_calculated": 10000.0,
                "vat_stated": 1200.0,
                "vat_expected_at_15_percent": 1500.0,
                "vat_variance": -300.0,
                "is_vat_valid": False,
            },
            "chronology_check": {
                "issue_date": "2026-10-20",
                "due_date": "2026-10-15",
                "is_chronology_valid": False,
                "warning": "Due date is prior to issue date.",
            },
            "discrepancies": [
                "Review the stated 12% tax rate against the configured company rules.",
                "Due date (Oct 15) precedes invoice issue date (Oct 20).",
            ],
        },
        "sample_text": (
            "TAX INVOICE / فاتورة ضريبية\n"
            "Invoice No: TX-2026-902\n"
            "Issue Date: 2026-10-20\n"
            "Due Date: 2026-10-15  <-- Note: Past date\n\n"
            "Items:\n"
            "1. IT Infrastructure Consulting (40 hrs @ $200/hr) = $8,000.00\n"
            "2. Network Security License (1 unit @ $2,000/ea) = $2,000.00\n\n"
            "Subtotal: $10,000.00\n"
            "VAT 12%: $1,200.00\n"
            "Total Invoiced: $11,200.00"
        ),
    },
    "summary": {
        "id": "summary",
        "name": "Executive Summary",
        "category": "general",
        "description": "Get a concise overview of your document's key points, metrics, and takeaways.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.2,
        "default_system_prompt": (
            "You are an executive briefing agent. Read the entire document, synthesize its core purpose, strategic takeaways, "
            "metrics, and recommended next steps. Return ONLY valid JSON."
        ),
        "default_query": "Provide a high-impact executive summary with core metrics and key action items.",
        "default_schema": {
            "title": "Executive Strategic Briefing",
            "purpose": "Evaluation of AI Document Intelligence migration for enterprise operations.",
            "key_takeaways": [
                "Automates 85% of manual invoice and contract workflows.",
                "Reduces invoice processing cycle time from 4 days to 45 seconds.",
                "Estimated annual operational savings of $420,000.",
            ],
            "metrics": {"efficiency_gain_percent": 85, "annual_savings_usd": 420000, "turnaround_time_seconds": 45},
            "recommended_actions": [
                "Pilot DOCTool on 1,000 historical supplier invoices.",
                "Integrate webhook callbacks with existing ERP system.",
            ],
        },
        "sample_text": (
            "STRATEGIC INITIATIVE REPORT: AI DOCUMENT AUTOMATION (OCTOBER 2026)\n\n"
            "EXECUTIVE OVERVIEW:\n"
            "This initiative assesses migrating our enterprise document ingestion to DOCTool AI Services.\n"
            "Our finance and legal departments currently review 12,000 invoices and 1,800 vendor contracts\n"
            "per year manually, creating approval bottlenecks of up to 4 business days.\n\n"
            "KEY FINDINGS:\n"
            "1. Accuracy: Automated vision OCR and structured JSON extraction achieves a 99.2% field fidelity rate.\n"
            "2. Speed: Average invoice parsing time drops from 25 minutes of manual data entry to 45 seconds.\n"
            "3. ROI: Net projected savings of $420,000 in Year 1 after implementation and API credits.\n\n"
            "NEXT STEPS:\n"
            "Authorize Phase 1 deployment across EMEA procurement teams starting next month."
        ),
    },
    "extraction": {
        "id": "extraction",
        "name": "Data Extraction",
        "category": "extraction",
        "description": "Pull tables, metrics, and numerical figures into structured Markdown or JSON.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.1,
        "default_system_prompt": (
            "You are a structured data extraction specialist. Locate and extract all tabular data, quantitative figures, "
            "and named entities. Return ONLY valid JSON."
        ),
        "default_query": "Extract all numerical tables and key parameters into structured records.",
        "default_schema": {
            "document_title": "Quarterly Operations Report",
            "tables": [
                {
                    "table_name": "Regional Production Output",
                    "columns": ["Region", "Q1_Units", "Q2_Units", "Growth_Pct"],
                    "rows": [
                        {"Region": "North America", "Q1_Units": 45000, "Q2_Units": 52000, "Growth_Pct": 15.5},
                        {"Region": "Europe", "Q1_Units": 38000, "Q2_Units": 41500, "Growth_Pct": 9.2},
                    ],
                }
            ],
            "total_records_extracted": 2,
        },
        "sample_text": (
            "QUARTERLY MANUFACTURING OUTPUT METRICS\n\n"
            "| Region | Q1 Units | Q2 Units | Growth % |\n"
            "| North America | 45,000 | 52,000 | +15.5% |\n"
            "| Europe | 38,000 | 41,500 | +9.2% |\n"
            "| Asia-Pacific | 62,000 | 74,000 | +19.3% |\n"
            "| Latin America | 18,500 | 20,100 | +8.6% |\n\n"
            "Global Total Units: 187,600 (Q2) vs 163,500 (Q1)."
        ),
    },
    "research": {
        "id": "research",
        "name": "Deep Research",
        "category": "general",
        "description": "Investigate claims, cross-reference sections, and gather grounded evidence.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.1,
        "default_system_prompt": (
            "You are a deep investigative research agent. Inspect claims with strict evidence grounding, "
            "gather supporting citations, identify inferences versus established facts, and synthesize conclusions. "
            "Return ONLY valid JSON."
        ),
        "default_query": "Conduct in-depth research on security certifications and data retention policies in this document.",
        "default_schema": {
            "research_topic": "Security Certifications and Data Retention",
            "grounded_findings": [
                {
                    "claim": "SOC 2 Type II certified annually",
                    "status": "VERIFIED",
                    "citation": "Section 4.2, Page 1",
                    "evidence": "Audit completed by Ernst & Young on August 15, 2026.",
                },
                {
                    "claim": "Customer data deleted within 30 days of termination",
                    "status": "VERIFIED",
                    "citation": "Section 7.1, Page 2",
                    "evidence": "All encrypted backups purged after 30-day grace period.",
                },
            ],
            "confidence_score": 0.96,
        },
        "sample_text": (
            "TRUST & SECURITY WHITE PAPER - CLOUD SCALE ENTERPRISE\n\n"
            "Section 4.2 - Compliance & Certifications:\n"
            "CloudScale undergoes annual SOC 2 Type II audits. The most recent audit was conducted by Ernst & Young\n"
            "and issued on August 15, 2026, confirming zero exceptions in Security and Confidentiality criteria.\n"
            "Additionally, CloudScale holds ISO/IEC 27001:2022 certification.\n\n"
            "Section 7.1 - Data Lifecycle & Retention:\n"
            "Upon contract termination, all primary customer databases are decommissioned within 72 hours.\n"
            "Encrypted disaster-recovery snapshots are securely overwritten and purged within thirty (30) days."
        ),
    },
    "chat": {
        "id": "chat",
        "name": "Document Chat",
        "category": "general",
        "description": "Ask questions and get answers grounded in your documents.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.3,
        "default_system_prompt": (
            "You are a helpful, precise document assistant. Answer user queries accurately using only the facts "
            "provided in the document. Cite exact pages or sections."
        ),
        "default_query": "What are the primary deliverables and delivery deadlines mentioned in the document?",
        "default_schema": {
            "answer": "The primary deliverables are the system architecture document due on Nov 15, 2026, and the production rollout due on Dec 20, 2026.",
            "citations": ["Page 1, Paragraph 3", "Page 2, Table 1"],
            "confidence": "High",
        },
        "sample_text": (
            "PROJECT CHARTER: CLOUD INFRASTRUCTURE UPGRADE\n\n"
            "Key Deliverables and Timeline:\n"
            "1. Architecture Design Document: Delivery due November 15, 2026.\n"
            "2. Staging Environment Deployment: Delivery due December 1, 2026.\n"
            "3. Production Cutover & Security Sign-off: Delivery due December 20, 2026.\n\n"
            "Project Lead: Sarah Connor, VP of Infrastructure."
        ),
    },
    "google_ai": {
        "id": "google_ai",
        "name": "Google AI Document",
        "category": "general",
        "description": "Multimodal document intelligence — layout hierarchy, entities, and tables.",
        "recommended_model": settings.DEFAULT_MODEL,
        "default_temperature": 0.1,
        "default_system_prompt": (
            "You are a multimodal document intelligence specialist. Analyze hierarchical document layout, "
            "extract key entities, tables, and visual structure. Return ONLY valid JSON."
        ),
        "default_query": "Analyze layout structure, header hierarchy, and entity relationships.",
        "default_schema": {
            "document_type": "Technical Specification",
            "layout_hierarchy": [
                {"level": 1, "heading": "System Architecture"},
                {"level": 2, "heading": "Database Cluster"},
            ],
            "entities": [{"type": "TECHNOLOGY", "text": "PostgreSQL 16"}, {"type": "METRIC", "text": "10,000 IOPS"}],
        },
        "sample_text": (
            "# SYSTEM ARCHITECTURE SPECIFICATION\n\n"
            "## 1. Database Cluster\n"
            "The backend utilizes PostgreSQL 16 with pgvector extension enabled for hybrid similarity search.\n"
            "Storage is provisioned on NVMe SSDs delivering 10,000 IOPS per node.\n\n"
            "## 2. In-Memory Caching\n"
            "Redis 7 serves as the primary session and message broker layer."
        ),
    },
}
