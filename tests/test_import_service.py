"""Tests for SMS / import parsing."""
from services.import_service import parse_sms_transaction_text


def test_parse_mpaisa_payment():
    text = "M-PAiSA: You have paid FJD 15.50 to MH Supermarket on 09/06/2026. Ref: 123456789."
    result = parse_sms_transaction_text(text)
    assert result is not None
    assert result["amount"] == -15.50
    assert "MH Supermarket" in result["description"]


def test_parse_received():
    text = "You have received FJD 100.00 from John Doe on 09/06/2026."
    result = parse_sms_transaction_text(text)
    assert result is not None
    assert result["amount"] == 100.0
    assert result.get("is_income") is True


def test_parse_vodafone():
    text = "Vodafone: You paid FJD 25.00 for Data Bundle on 10/06/2026."
    result = parse_sms_transaction_text(text)
    assert result is not None
    assert result["amount"] == -25.0
