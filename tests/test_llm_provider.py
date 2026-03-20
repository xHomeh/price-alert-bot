from __future__ import annotations

from pydantic import ValidationError

from carousell_alert_bot.providers.llm import OpenAILLMProvider


def test_llm_response_parser_accepts_plain_json_and_fenced_json() -> None:
    plain = """
    {
      "normalized_brand": "Sony",
      "normalized_model": "WH-1000XM5",
      "condition_grade": "B",
      "condition_notes": "Minor wear",
      "estimated_fair_price_min_cents": 26000,
      "estimated_fair_price_max_cents": 32000,
      "deal_score": 91.2,
      "should_alert": true,
      "alert_reason": "Strong discount versus expected resale value.",
      "confidence": 0.89
    }
    """
    parsed = OpenAILLMProvider._parse_json_output(plain)
    assert parsed.normalized_brand == "Sony"
    assert parsed.should_alert is True

    fenced = f"```json\n{plain}\n```"
    parsed_fenced = OpenAILLMProvider._parse_json_output(fenced)
    assert parsed_fenced.estimated_fair_price_max_cents == 32_000


def test_llm_response_parser_rejects_missing_fields() -> None:
    invalid = '{"normalized_brand": "Sony"}'
    try:
        OpenAILLMProvider._parse_json_output(invalid)
    except ValidationError as exc:
        assert "condition_grade" in str(exc)
    else:
        raise AssertionError("Expected a validation error for incomplete LLM JSON.")

