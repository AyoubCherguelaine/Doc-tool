"""Unit and API tests for model selection from models.json and logical credit calculation.

Enforces:
1. Only models defined in models.json are allowed.
2. Credit pricing logic: $2.00 USD = 1,000 credits ($0.002 / credit).
3. Model validation rejects any unauthorized model.
4. Service cost calculation dynamically incorporates model fees.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.models_config import CREDIT_PRICE_USD, USD_TO_CREDITS_RATE, model_registry
from backend.billing import billing_service
from backend.server import app


def test_models_json_loaded_properly():
    """Verify models.json is loaded and contains the expected models."""
    models = model_registry.get_all_models()
    assert len(models) >= 11
    
    ids = model_registry.allowed_model_ids
    assert "gpt-4o-mini" in ids
    assert "gpt-4o" in ids
    assert "gpt-6-luna" in ids
    assert "gpt-5-nano" in ids
    assert "o3-mini" in ids
    assert "o1-mini" in ids
    assert "gpt-4.1-mini" in ids
    assert "gpt-5.4-nano" in ids
    assert "gpt-5.6-luna" in ids


def test_economic_rate_constants():
    """Verify $2.00 is 1,000 credits."""
    assert CREDIT_PRICE_USD == 0.002
    assert USD_TO_CREDITS_RATE == 500.0
    # $2.00 should equal 1,000 credits
    assert 2.00 * USD_TO_CREDITS_RATE == 1000.0
    assert 1000 * CREDIT_PRICE_USD == 2.00


def test_model_validation_strictness():
    """Verify ONLY models in models.json are permitted."""
    # Valid models
    assert model_registry.validate_model("gpt-4o-mini") == "gpt-4o-mini"
    assert model_registry.validate_model("gpt-6-luna") == "gpt-6-luna"
    assert model_registry.validate_model("o3-mini") == "o3-mini"
    assert model_registry.validate_model(None) == model_registry.default_model_id
    assert model_registry.validate_model("") == model_registry.default_model_id

    # Disallowed models must raise HTTPException 400
    with pytest.raises(HTTPException) as exc:
        model_registry.validate_model("claude-3-opus")
    assert exc.value.status_code == 400
    assert "not permitted" in exc.value.detail.lower()

    with pytest.raises(HTTPException) as exc:
        model_registry.validate_model("gpt-3.5-turbo")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        model_registry.validate_model("unknown-custom-model")
    assert exc.value.status_code == 400


def test_service_credit_calculation_logic():
    """Test logical credit consumption based on service complexity and chosen model."""
    # Baseline: invoice has 25 base credits; gpt-4o-mini has credit_cost 5 (default baseline)
    cost_default = billing_service.get_service_cost("invoice", "gpt-4o-mini")
    assert cost_default == 25

    # Cheaper model: gpt-5-nano has credit_cost 2 (3 credits cheaper than baseline)
    cost_nano = billing_service.get_service_cost("invoice", "gpt-5-nano")
    assert cost_nano == 22

    # Flagship model: gpt-4o has credit_cost 15 (+10 credits above baseline)
    cost_gpt4o = billing_service.get_service_cost("invoice", "gpt-4o")
    assert cost_gpt4o == 35

    # Heavy reasoning model: o3-mini has credit_cost 30 (+25 credits above baseline)
    cost_o3 = billing_service.get_service_cost("invoice", "o3-mini")
    assert cost_o3 == 50

    # Detailed breakdown test
    calc = model_registry.calculate_service_cost(25, "gpt-4o")
    assert calc["base_service_credits"] == 25
    assert calc["model_credit_cost"] == 15
    assert calc["model_delta"] == 10
    assert calc["total_credits"] == 35
    assert calc["total_cost_usd"] == 35 * 0.002
    assert calc["total_cost_usd_formatted"] == "$0.070"


def test_api_models_endpoint():
    """Verify GET /api/v1/models returns enriched models with credit calculations."""
    client = TestClient(app)
    res = client.get("/api/v1/models")
    assert res.status_code == 200
    data = res.json()
    assert data["object"] == "list"
    assert data["total_available"] >= 11
    assert data["credit_price_usd"] == 0.002

    # Check a specific model
    gpt4o = next(m for m in data["data"] if m["id"] == "gpt-4o")
    assert gpt4o["credit_cost"] == 15
    assert gpt4o["cost_usd"] == 0.030
    assert gpt4o["cost_usd_formatted"] == "$0.030"
    assert gpt4o["pricing"]["input_per_million"] == 2.5
    assert gpt4o["token_credits"]["input_per_million"] == 1250.0  # 2.5 * 500


def test_calculate_cost_endpoint():
    """Verify POST /api/services/calculate-cost endpoint."""
    client = TestClient(app)
    res = client.post(
        "/api/services/calculate-cost",
        json={"service": "summary", "model": "gpt-6-luna"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["base_service_credits"] == 10
    assert data["model_id"] == "gpt-6-luna"
    # gpt-6-luna credit_cost is 4 (delta = 4 - 5 = -1)
    assert data["total_credits"] == 9
    assert data["total_cost_usd"] == pytest.approx(9 * 0.002)
    assert data["total_cost_usd_formatted"] == "$0.018"
    assert data["guardian"] is True
    assert data["guardian_fee"] == 5

    # Direct return mode (guardian=False) discounts the 5 cr guardian verification fee
    res_direct = client.post(
        "/api/services/calculate-cost",
        json={"service": "summary", "model": "gpt-6-luna", "guardian": False},
    )
    assert res_direct.status_code == 200
    data_direct = res_direct.json()
    assert data_direct["guardian"] is False
    assert data_direct["guardian_fee"] == 0
    assert data_direct["guardian_discount"] == 5
    # 9 - 5 = 4 credits
    assert data_direct["total_credits"] == 4
    assert data_direct["total_cost_usd"] == pytest.approx(4 * 0.002)


def test_guardian_billing_and_direct_return_logic():
    """Verify guardian takes credit fee when enabled, and discounts fee when direct mode is selected."""
    # invoice base is 25 credits with gpt-4o-mini
    cost_guardian_on = billing_service.get_service_cost("invoice", "gpt-4o-mini", guardian=True)
    assert cost_guardian_on == 25

    cost_guardian_off = billing_service.get_service_cost("invoice", "gpt-4o-mini", guardian=False)
    # Waives 5 credits fee: 25 - 5 = 20
    assert cost_guardian_off == 20

    # Low-cost service: chat base is 1 credit; min cost is always 1
    cost_chat_guardian_off = billing_service.get_service_cost("chat", "gpt-4o-mini", guardian=False)
    assert cost_chat_guardian_off == 1


def test_guardian_settings_api():
    """Verify company guardian setting endpoints."""
    from backend.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {"id": "test-user-guardian-1", "name": "Guardian Tester"}
    try:
        client = TestClient(app)

        # Default should be enabled
        get_res = client.get("/api/settings/guardian")
        assert get_res.status_code == 200
        assert get_res.json()["guardian"] is True
        assert get_res.json()["guardianFeeCredits"] == 5

        # Set to disabled (direct return mode)
        post_res = client.post("/api/settings/guardian", json={"enabled": False})
        assert post_res.status_code == 200
        assert post_res.json()["guardian"] is False
        assert post_res.json()["mode"] == "direct_return"

        # Confirm updated setting
        get_res_2 = client.get("/api/settings/guardian")
        assert get_res_2.status_code == 200
        assert get_res_2.json()["guardian"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_user_dedicated_workspace_api():
    """Verify each user gets their own dedicated workspace and can rename it."""
    from backend.auth import get_current_user

    # User 1: Ayoub
    app.dependency_overrides[get_current_user] = lambda: {"id": "user-ayoub-101", "name": "Ayoub", "email": "ayoub@example.com"}
    try:
        client = TestClient(app)
        res = client.get("/api/workspace")
        assert res.status_code == 200
        data = res.json()
        assert data["userId"] == "user-ayoub-101"
        assert "Ayoub" in data["name"]
        assert data["status"] == "active"
        assert data["remainingCredits"] >= 300

        # Rename workspace
        put_res = client.put("/api/workspace", json={"name": "Ayoub AI Analytics Lab"})
        assert put_res.status_code == 200
        assert put_res.json()["name"] == "Ayoub AI Analytics Lab"

        # Verify updated workspace name persists
        res_after = client.get("/api/workspace")
        assert res_after.json()["name"] == "Ayoub AI Analytics Lab"
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # User 2: Separate user gets their own distinct workspace
    app.dependency_overrides[get_current_user] = lambda: {"id": "user-other-202", "name": "Sarah", "email": "sarah@example.com"}
    try:
        client = TestClient(app)
        res2 = client.get("/api/workspace")
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["userId"] == "user-other-202"
        assert data2["name"] != "Ayoub AI Analytics Lab"
        assert "Sarah" in data2["name"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_advanced_ocr_model_validation_and_handling():
    """Verify Advanced OCR endpoint validates and accepts model parameter."""
    import uuid
    from unittest.mock import patch
    from backend.v1.routes import get_company_or_api_auth
    from backend.billing import CompanyAccount

    mock_account = CompanyAccount(
        id=str(uuid.uuid4()),
        user_id="user-ocr-test",
        company_name="Test OCR Co",
        plan_tier="standard",
        total_credits=1000,
        used_credits=0,
        api_key="docu_live_1234567890abcdef",
        api_key_prefix="docu_live_1234",
        is_active=True,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )
    app.dependency_overrides[get_company_or_api_auth] = lambda: mock_account

    client = TestClient(app)
    try:
        # Invalid model in form-data should fail with 400
        fake_pdf = b"%PDF-1.4 sample pdf content %%EOF"
        files = {"file": ("test.pdf", fake_pdf, "application/pdf")}
        data = {"model": "non-existent-model", "start_page": "1"}
        res = client.post("/api/v1/ocr/advanced", files=files, data=data)
        assert res.status_code == 400
        assert "not permitted" in res.json()["detail"].lower()

        # Valid model should be accepted
        with patch("backend.v1.routes.validate_pdf_pages"), \
             patch("backend.v1.routes.run_in_threadpool", return_value={"blocks": [], "total_pages": 1, "ocr_text": "hello"}):
            files = {"file": ("test.pdf", fake_pdf, "application/pdf")}
            data = {"model": "gpt-6-luna", "start_page": "1"}
            res_valid = client.post("/api/v1/ocr/advanced", files=files, data=data)
            assert res_valid.status_code == 200
            assert res_valid.json()["model"] == "gpt-6-luna"
            assert res_valid.json()["status"] == "success"
            assert res_valid.json()["credits_deducted"] == 4
            assert res_valid.json()["credits_remaining"] == 996
            assert mock_account.remaining_credits == 996
    finally:
        app.dependency_overrides.pop(get_company_or_api_auth, None)

