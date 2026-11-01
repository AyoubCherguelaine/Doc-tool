"""
Bilingual Fraud, Anomaly & Arithmetic Audit Agent.

Specialises in inspecting documents for mathematical discrepancies,
tax calculation errors (configurable VAT), inverted dates (due before issue date),
and contractual contradictions in English and Arabic documents.
"""

from __future__ import annotations

import json
from typing import Optional

from backend.agent.agents.base import BaseAgent, BaseAgentConfig
from backend.agent.tools.bilingual import BilingualDocumentKit
from backend.agent.tools.registry import Tool

ANOMALY_AUDIT_PROMPT = """\
You are an Enterprise Forensic Document Auditor and Fraud Prevention Specialist fluent in English and Arabic.
Your objective is to inspect documents for mathematical discrepancies, tax errors,
date logic flaws, and contractual contradictions. Unknown or ambiguous inputs must be reported as not checked.

Checks to perform:
1. **Arithmetic Integrity**: Check subtotal + tax = total, quantity * unit price = total line item.
2. **VAT / Tax Logic**: Check the stated or configured tax rate. Never assume 15% or any country-specific rate.
3. **Date Logic**: Verify due date does not precede issue date, check contract expiration and milestones.
4. **Contractual Contradictions**: Identify if clauses in one section contradict terms in another.
5. **Assign Overall Risk Rating**: CLEAN (سليم), MEDIUM_RISK (تنبيه متوسط), HIGH_RISK (مخاطر عالية), CRITICAL_ALERT (إنذار حرج).

Process:
1. Search and inspect the document using search_documents or read_page.
2. Run audit_anomalies to automatically detect math and date discrepancies.
3. Structure your audit report:
   - ## Forensic Audit Executive Verdict (القرار التنفيذي لتدقيق الوثيقة)
   - ## Arithmetic & Tax Findings (ملاحظات الحسابات والضريبة)
   - ## Date & Chronology Logic (تسلسل التواريخ والاستحقاق)
   - ## Recommended Remediation (التوصيات والإجراءات التصحيحية)
"""


class AnomalyAuditAgent(BaseAgent):
    """Agent specialised in detecting arithmetic errors, tax mismatches, and fraud anomalies in EN & AR."""

    def __init__(
        self,
        llm,
        tool_kit,
        config: Optional[BaseAgentConfig] = None,
    ):
        base_cfg = config or BaseAgentConfig()
        base_cfg.system_prompt = base_cfg.system_prompt or ANOMALY_AUDIT_PROMPT
        base_cfg.max_iterations = 10
        super().__init__(llm, tool_kit, base_cfg)

    def _register_tools(self) -> None:
        """Register document tools + anomaly audit tool."""
        if hasattr(self.tool_kit, "register_all"):
            self.tool_kit.register_all(self.registry)

        self.registry.register(
            Tool(
                name="audit_anomalies",
                description="Audit arithmetic consistency, configured VAT calculations, and chronological date logic.",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Document text to audit."},
                    },
                    "required": ["text"],
                },
                func=lambda text: json.dumps(BilingualDocumentKit.audit_anomalies(text), ensure_ascii=False),
            )
        )
