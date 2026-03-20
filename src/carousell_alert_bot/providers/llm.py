from __future__ import annotations

import json
from typing import Any

from carousell_alert_bot.contracts import (
    ComparisonSnapshot,
    LLMEvaluationResult,
    ReferencePriceSnapshot,
    ScrapedListing,
)

SYSTEM_PROMPT = """You are a strict resale-market analyst for Carousell Singapore.
Return JSON only. Do not include markdown fences.
Assess the listing based on the title, description, image URLs, comparable prices,
reference retail prices, and the user's alert preference. The response must contain:
normalized_brand, normalized_model, condition_grade, condition_notes,
estimated_fair_price_min_cents, estimated_fair_price_max_cents, deal_score,
should_alert, alert_reason, confidence.
Use integer cents for price fields, a float from 0 to 1 for confidence,
and a float from 0 to 100 for deal_score.
If evidence is weak, lower confidence and be conservative about alerts."""


class OpenAILLMProvider:
    def __init__(self, *, api_key: str | None, model_name: str) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self._client = None

    async def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    @staticmethod
    def _parse_json_output(output_text: str) -> LLMEvaluationResult:
        cleaned = output_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("json", "", 1).strip()
        payload = json.loads(cleaned)
        return LLMEvaluationResult.model_validate(payload)

    async def evaluate_candidate(
        self,
        *,
        listing: ScrapedListing,
        user_alert_style: str,
        max_price_cents: int,
        comparison_snapshot: ComparisonSnapshot,
        reference_snapshot: ReferencePriceSnapshot,
    ) -> LLMEvaluationResult:
        client = await self._get_client()
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "user_alert_style": user_alert_style,
                        "watch_max_price_cents": max_price_cents,
                        "listing": listing.model_dump(mode="json"),
                        "comparison_snapshot": comparison_snapshot.model_dump(),
                        "reference_snapshot": reference_snapshot.model_dump(mode="json"),
                    },
                    indent=2,
                    sort_keys=True,
                ),
            }
        ]
        for image_url in listing.image_urls[:4]:
            content.append({"type": "input_image", "image_url": str(image_url)})

        response = await client.responses.create(
            model=self.model_name,
            instructions=SYSTEM_PROMPT,
            input=[{"role": "user", "content": content}],
        )
        output_text = getattr(response, "output_text", "")
        if not output_text:
            raise ValueError("OpenAI response did not contain text output.")
        return self._parse_json_output(output_text)
