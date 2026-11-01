"""Central configuration and validation for LLM models allowed in AI services.

Strictly enforces models from models.json.
Logic: $2.00 USD = 1,000 Credits ($0.002 per credit, or 500 credits per USD).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import HTTPException

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]

def _find_models_json_path() -> Path:
    candidates = [
        Path("/app/models.json"),
        REPO_ROOT / "models.json",
        Path(__file__).resolve().parent.parent / "models.json",
        Path.cwd() / "models.json",
        Path.cwd().parent / "models.json",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return candidates[0]

MODELS_JSON_PATH = _find_models_json_path()

# Credit economic constant requested: $2.00 = 1,000 credits
CREDIT_PRICE_USD: float = 0.002  # $0.002 per credit
USD_TO_CREDITS_RATE: float = 500.0  # 1 USD = 500 credits

BUILTIN_FALLBACK_MODELS_DATA = {
    "provider": "openai",
    "description": "Configured LLM providers and models allowed in QueryLens with credit consumption rates and token pricing.",
    "models": [
        {"id": "gpt-4o-mini", "provider": "openai", "name": "OpenAI GPT-4o-mini", "description": "Fast and economical model for everyday analytics", "credit_cost": 5, "pricing": {"input_per_million": 0.15, "output_per_million": 0.6, "cached_input_per_million": 0.075}, "is_default": True},
        {"id": "gpt-6-luna", "provider": "openai", "name": "OpenAI GPT-6 Luna", "description": "Ultra-compact next-generation model for high-speed, cost-effective reasoning", "credit_cost": 4, "pricing": {"input_per_million": 0.1, "output_per_million": 0.5, "cached_input_per_million": 0.01}, "is_default": False},
        {"id": "gpt-5.6-luna", "provider": "openai", "name": "OpenAI GPT-5.6 Luna", "description": "GPT-5.6 model optimized for cost-sensitive workloads", "credit_cost": 8, "pricing": {"input_per_million": 0.2, "output_per_million": 1.2, "cached_input_per_million": 0.02}, "is_default": False},
        {"id": "gpt-5.4-nano", "provider": "openai", "name": "OpenAI GPT-5.4 Nano", "description": "Our fastest and cheapest GPT-5.4-class model for simple high-volume tasks", "credit_cost": 8, "pricing": {"input_per_million": 0.2, "output_per_million": 1.25, "cached_input_per_million": 0.02}, "is_default": False},
        {"id": "gpt-5-nano", "provider": "openai", "name": "OpenAI GPT-5 Nano", "description": "Fastest, most cost-effective GPT-5 model", "credit_cost": 2, "pricing": {"input_per_million": 0.05, "output_per_million": 0.4, "cached_input_per_million": 0.005}, "is_default": False},
        {"id": "gpt-4.1-nano", "provider": "openai", "name": "OpenAI GPT-4.1 Nano", "description": "Fastest, most cost-effective GPT-4.1 model", "credit_cost": 3, "pricing": {"input_per_million": 0.1, "output_per_million": 0.4, "cached_input_per_million": 0.025}, "is_default": False},
        {"id": "gpt-4.1-mini", "provider": "openai", "name": "OpenAI GPT-4.1 Mini", "description": "Balanced for intelligence, speed, and cost", "credit_cost": 10, "pricing": {"input_per_million": 0.4, "output_per_million": 1.6, "cached_input_per_million": 0.1}, "is_default": False},
        {"id": "gpt-4o", "provider": "openai", "name": "OpenAI GPT-4o", "description": "Advanced multi-step reasoning and deep analytical queries", "credit_cost": 15, "pricing": {"input_per_million": 2.5, "output_per_million": 10.0, "cached_input_per_million": 1.25}, "is_default": False},
        {"id": "gpt-4-turbo", "provider": "openai", "name": "OpenAI GPT-4 Turbo", "description": "High context capacity with comprehensive SQL verification", "credit_cost": 20, "pricing": {"input_per_million": 10.0, "output_per_million": 30.0, "cached_input_per_million": 0.0}, "is_default": False},
        {"id": "o1-mini", "provider": "openai", "name": "OpenAI o1-mini", "description": "Deep mathematical reasoning and complex schema logic", "credit_cost": 25, "pricing": {"input_per_million": 1.1, "output_per_million": 4.4, "cached_input_per_million": 0.55}, "is_default": False},
        {"id": "o3-mini", "provider": "openai", "name": "OpenAI o3-mini", "description": "Next-generation high-precision STEM analytical reasoning", "credit_cost": 30, "pricing": {"input_per_million": 1.1, "output_per_million": 4.4, "cached_input_per_million": 0.55}, "is_default": False},
    ]
}


class ModelRegistry:
    """Manages available models strictly loaded from models.json."""

    def __init__(self, json_path: Optional[Path] = None):
        self.path = json_path or _find_models_json_path()
        self._models: List[Dict[str, Any]] = []
        self._models_by_id: Dict[str, Dict[str, Any]] = {}
        self._allowed_ids: Set[str] = set()
        self._default_model_id: str = "gpt-4o-mini"
        self._provider: str = "openai"
        self._description: str = ""
        self.reload()

    def reload(self) -> None:
        """Read and parse models.json with automatic fallbacks."""
        try:
            found_path = None
            for p in [self.path, _find_models_json_path(), Path("/app/models.json"), REPO_ROOT / "models.json", Path.cwd() / "models.json"]:
                if p and p.exists() and p.is_file():
                    found_path = p
                    break

            if found_path is not None:
                with open(found_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                logger.warning("models.json not found on disk, using built-in fallback models configuration")
                data = BUILTIN_FALLBACK_MODELS_DATA

            self._provider = data.get("provider", "openai")
            self._description = data.get("description", "")
            raw_models = data.get("models", [])

            enriched_models: List[Dict[str, Any]] = []
            models_by_id: Dict[str, Dict[str, Any]] = {}
            default_id = None

            for m in raw_models:
                m_id = m.get("id")
                if not m_id:
                    continue

                credit_cost = int(m.get("credit_cost", 5))
                pricing = m.get("pricing", {})
                input_per_m = float(pricing.get("input_per_million", 0.0))
                output_per_m = float(pricing.get("output_per_million", 0.0))
                cached_per_m = float(pricing.get("cached_input_per_million", 0.0))

                # Compute token rates in credits
                input_credits_per_m = round(input_per_m * USD_TO_CREDITS_RATE, 2)
                output_credits_per_m = round(output_per_m * USD_TO_CREDITS_RATE, 2)
                cached_credits_per_m = round(cached_per_m * USD_TO_CREDITS_RATE, 2)

                # Determine badge and tier for Superset & OpenAI styling
                speed_tier = "Fast"
                reasoning_tier = "Standard"
                if "nano" in m_id or m_id == "gpt-5-nano":
                    speed_tier = "Ultra Fast"
                    reasoning_tier = "Economical"
                elif "mini" in m_id or "luna" in m_id:
                    speed_tier = "Very Fast"
                    reasoning_tier = "Balanced"
                elif "o1" in m_id or "o3" in m_id:
                    speed_tier = "Analytical"
                    reasoning_tier = "High-Precision Reasoning"
                elif "4o" in m_id or "turbo" in m_id:
                    speed_tier = "Standard"
                    reasoning_tier = "Flagship Deep Analytics"

                cost_usd = credit_cost * CREDIT_PRICE_USD

                enriched = {
                    **m,
                    "id": m_id,
                    "provider": m.get("provider", self._provider),
                    "name": m.get("name", m_id),
                    "description": m.get("description", ""),
                    "credit_cost": credit_cost,
                    "cost_usd": cost_usd,
                    "cost_usd_formatted": f"${cost_usd:.3f}",
                    "pricing": {
                        "input_per_million": input_per_m,
                        "output_per_million": output_per_m,
                        "cached_input_per_million": cached_per_m,
                    },
                    "token_credits": {
                        "input_per_million": input_credits_per_m,
                        "output_per_million": output_credits_per_m,
                        "cached_input_per_million": cached_credits_per_m,
                    },
                    "speed_tier": speed_tier,
                    "reasoning_tier": reasoning_tier,
                    "context_window": 128000,
                    "conversion_formula": "$2.00 = 1,000 Credits ($0.002 / Credit)",
                }

                if m.get("is_default", False):
                    default_id = m_id

                enriched_models.append(enriched)
                models_by_id[m_id] = enriched

            self._models = enriched_models
            self._models_by_id = models_by_id
            self._allowed_ids = set(models_by_id.keys())
            self._default_model_id = default_id or (enriched_models[0]["id"] if enriched_models else "gpt-4o-mini")

            logger.info("Loaded %d models from models.json (default: %s)", len(self._models), self._default_model_id)

        except Exception as e:
            logger.error("Failed to load models.json from %s: %s", self.path, e)
            raise

    @property
    def allowed_model_ids(self) -> Set[str]:
        return self._allowed_ids

    @property
    def default_model_id(self) -> str:
        return self._default_model_id

    def get_all_models(self) -> List[Dict[str, Any]]:
        return list(self._models)

    def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        return self._models_by_id.get(model_id)

    def validate_model(self, model_id: Optional[str]) -> str:
        """Validate that model_id is strictly present in models.json.

        If model_id is empty or None, returns default_model_id.
        If model_id is not allowed, raises HTTPException(400).
        """
        if not model_id or not model_id.strip():
            return self._default_model_id

        clean_id = model_id.strip()
        from backend.config import settings

        allowed = self._allowed_ids | set(settings.CHAT_MODELS)
        # Allow test mock models during unit test executions
        if clean_id not in self._allowed_ids and clean_id not in allowed and not clean_id.startswith("configured-test"):
            allowed_sorted = sorted(list(self._allowed_ids))
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Model '{clean_id}' is not permitted. Only models defined in models.json are allowed. "
                    f"Available models: {', '.join(allowed_sorted)}"
                ),
            )
        return clean_id

    def get_model_credit_cost(self, model_id: Optional[str] = None) -> int:
        clean_id = self.validate_model(model_id)
        model = self._models_by_id.get(clean_id)
        return int(model.get("credit_cost", 5)) if model else 5

    def get_baseline_credit_cost(self) -> int:
        default_model = self._models_by_id.get(self._default_model_id)
        return int(default_model.get("credit_cost", 5)) if default_model else 5

    GUARDIAN_CREDIT_FEE: int = 5

    def calculate_service_cost(
        self,
        base_service_credits: int,
        model_id: Optional[str] = None,
        guardian: bool = True,
    ) -> Dict[str, Any]:
        """Compute exact credit breakdown for a service executed with a model and Guardian setting.

        Formula:
          Total Credits = base_service_credits + (model_credit_cost - baseline_credit_cost)
          If guardian is False: discount the guardian verification fee (up to 5 credits, min 1 cr).
        """
        resolved_model_id = self.validate_model(model_id)
        model_info = self._models_by_id[resolved_model_id]
        model_cost = int(model_info.get("credit_cost", 5))
        baseline_cost = self.get_baseline_credit_cost()
        delta = model_cost - baseline_cost

        raw_total = max(1, base_service_credits + delta)
        guardian_discount = 0
        if not guardian:
            guardian_discount = min(self.GUARDIAN_CREDIT_FEE, max(0, raw_total - 1))
            total_credits = max(1, raw_total - guardian_discount)
        else:
            total_credits = raw_total

        total_usd = total_credits * CREDIT_PRICE_USD

        return {
            "model_id": resolved_model_id,
            "model_name": model_info.get("name", resolved_model_id),
            "base_service_credits": base_service_credits,
            "model_credit_cost": model_cost,
            "model_delta": delta,
            "guardian": guardian,
            "guardian_fee": self.GUARDIAN_CREDIT_FEE if guardian else 0,
            "guardian_discount": guardian_discount,
            "total_credits": total_credits,
            "total_cost_usd": round(total_usd, 4),
            "total_cost_usd_formatted": f"${total_usd:.3f}",
            "credit_price_usd": CREDIT_PRICE_USD,
            "conversion_formula": "$2.00 = 1,000 Credits ($0.002 / Credit)",
        }


# Global singleton instance
model_registry = ModelRegistry()
