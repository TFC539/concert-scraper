from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import requests


OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
logger = logging.getLogger(__name__)


class OpenRouterExtractionError(RuntimeError):
    pass


class OpenRouterDisambiguationError(RuntimeError):
    pass


@dataclass
class OpenRouterConfig:
    api_key: str
    model: str
    timeout_seconds: int = 40
    max_retries: int = 2
    app_name: str = "concert-scraper"
    app_url: str = "https://localhost"


def _preview_text(value: str, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def load_openrouter_config(overrides: dict[str, Any] | None = None) -> OpenRouterConfig | None:
    overrides = overrides or {}

    override_api_key = str(overrides.get("api_key", "") or "").strip()
    api_key = override_api_key or os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        logger.info("openrouter_config_missing_api_key")
        return None

    model = str(overrides.get("model") or os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini")).strip()
    if not model:
        model = "openai/gpt-4.1-mini"

    timeout_raw = overrides.get("timeout_seconds")
    retries_raw = overrides.get("max_retries")
    timeout_value = timeout_raw if timeout_raw is not None else os.getenv("OPENROUTER_TIMEOUT_SECONDS", "40")
    retries_value = retries_raw if retries_raw is not None else os.getenv("OPENROUTER_MAX_RETRIES", "2")
    try:
        timeout_seconds = int(timeout_value)
    except (TypeError, ValueError):
        logger.warning("openrouter_config_invalid_timeout value=%s fallback=40", timeout_value)
        timeout_seconds = 40
    try:
        max_retries = int(retries_value)
    except (TypeError, ValueError):
        logger.warning("openrouter_config_invalid_max_retries value=%s fallback=2", retries_value)
        max_retries = 2
    app_name = os.getenv("OPENROUTER_APP_NAME", "concert-scraper").strip() or "concert-scraper"
    app_url = os.getenv("OPENROUTER_APP_URL", "https://localhost").strip() or "https://localhost"

    config = OpenRouterConfig(
        api_key=api_key,
        model=model,
        timeout_seconds=max(5, timeout_seconds),
        max_retries=max(0, max_retries),
        app_name=app_name,
        app_url=app_url,
    )
    logger.info(
        "openrouter_config_loaded model=%s timeout_seconds=%s max_retries=%s app_name=%s app_url=%s",
        config.model,
        config.timeout_seconds,
        config.max_retries,
        config.app_name,
        config.app_url,
    )
    return config


def _build_messages(raw_text: str) -> list[dict[str, str]]:
    system_prompt = (
        "Extract concert entities as strict JSON only. "
        "Return keys p (performers), w (works), v (venue), optional d (date), s (sold_out boolean), and pt (price_tags string list). "
        "Normalize to atomic list items: each performer must be one person or ensemble name only; each work must be one composition in program order. "
        "Do not combine multiple performers or works into one string item. "
        "Input may contain sections Event Metadata, Performers, and Programme with bullet lines. Prefer explicit values from those sections. "
        "Ignore non-entity labels like Start, End, Series, Find out more, Promoter, Supported by, and booklet/pdf references. "
        "For performer lines with roles/instruments, keep only the person or ensemble name. "
        "Treat ticketing lines as evidence for sold_out and pt, not as works. "
        "Extract concise ticket price tags exactly as shown in text when present (examples: 'EUR 39', '$45', 'ab 20 EUR', 'Free'). "
        "Each work item must include c (composer) and t (title), using empty strings when unknown. "
        "Do not match to external databases and do not add explanations or markdown."
    )
    user_prompt = (
        "Concert listing text:\n"
        f"{raw_text}\n\n"
        "Return JSON schema:\n"
        '{"p": ["string"], "w": [{"c": "string", "t": "string"}], "v": "string", "d": "string optional", "s": "boolean optional", "pt": ["string"]}'
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    logger.info(
        "openrouter_prompt_built raw_text_chars=%s raw_text_lines=%s system_prompt_chars=%s user_prompt_chars=%s raw_preview=%s",
        len(raw_text or ""),
        len((raw_text or "").splitlines()),
        len(system_prompt),
        len(user_prompt),
        _preview_text(raw_text),
    )
    return messages


def _build_disambiguation_messages(
    entity_type: str,
    raw_text: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    system_prompt = (
        "Resolve ambiguous concert entities. "
        "Choose exactly one candidate id when the evidence is strong, otherwise choose null. "
        "Return strict JSON only with keys id, confidence, and reason."
    )
    user_prompt = (
        f"Entity type: {entity_type}\n"
        f"Input text: {raw_text}\n"
        f"Candidates JSON: {json.dumps(candidates, ensure_ascii=True)}\n\n"
        "Return JSON schema:\n"
        '{"id": "integer|null", "confidence": 0.0, "reason": "string"}'
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _serialize_disambiguation_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        try:
            candidate_id = int(raw_id)
        except (TypeError, ValueError):
            continue

        label = str(item.get("label", "") or "").strip()
        try:
            score = float(item.get("score", 0.0) or 0.0)
        except (TypeError, ValueError):
            score = 0.0

        serialized.append(
            {
                "id": candidate_id,
                "label": label,
                "score": round(max(0.0, min(1.0, score)), 4),
            }
        )

    return serialized


def _as_string_list(values: Any, split_pattern: str | None = None) -> list[str]:
    if not isinstance(values, list):
        return []

    seen: set[str] = set()
    output: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if not text:
            continue

        parts = [text]
        if split_pattern:
            parts = [part.strip() for part in re.split(split_pattern, text) if part.strip()]

        for part in parts:
            lowered = part.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            output.append(part)
    return output


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value or "").strip().lower()
    if not text:
        return default
    if text in {"true", "yes", "y", "1", "sold out", "ausverkauft"}:
        return True
    if text in {"false", "no", "n", "0", "available", "tickets available"}:
        return False
    return default


def _normalize_price_tags(values: Any) -> list[str]:
    tags = _as_string_list(values, split_pattern=r"\n+|\s*\|\s*|\s*;\s*")
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        compact = re.sub(r"\s+", " ", tag).strip()
        if not compact:
            continue
        key = compact.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(compact)
    return normalized


def _validate_extraction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    performers = _as_string_list(
        payload.get("p", []),
        split_pattern=r"\n+|\s*\|\s*|\s*/\s*|\s*;\s*|\s*&\s*|\s+[Uu][Nn][Dd]\s+|\s+[Aa][Nn][Dd]\s+",
    )

    works_input = payload.get("w", [])
    works: list[dict[str, str]] = []
    seen_work_keys: set[tuple[str, str]] = set()
    if isinstance(works_input, list):
        for item in works_input:
            if not isinstance(item, dict):
                continue
            composer = str(item.get("c", "") or "").strip()
            title = str(item.get("t", "") or "").strip()
            if not composer and not title:
                continue

            title_parts = [title]
            if title:
                title_parts = [part.strip() for part in re.split(r"\n+|\s*\|\s*|\s*;\s*|\s*/\s*", title) if part.strip()]

            for title_part in title_parts or [""]:
                normalized_title = title_part or ""
                work_key = (composer.lower(), normalized_title.lower())
                if work_key in seen_work_keys:
                    continue
                seen_work_keys.add(work_key)
                works.append({"c": composer, "t": normalized_title})

    venue = str(payload.get("v", "") or "").strip()
    date_text = str(payload.get("d", "") or "").strip()
    sold_out = _as_bool(payload.get("s"), default=False)
    price_tags = _normalize_price_tags(payload.get("pt", []))

    return {
        "p": performers,
        "w": works,
        "v": venue,
        "d": date_text,
        "s": sold_out,
        "pt": price_tags,
    }


def _validate_disambiguation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    selected_id: int | None
    raw_id = payload.get("id")
    if raw_id is None:
        selected_id = None
    else:
        try:
            selected_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise OpenRouterDisambiguationError("Disambiguation response id must be an integer or null") from exc

    try:
        confidence = float(payload.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    reason = str(payload.get("reason", "") or "").strip()
    return {
        "id": selected_id,
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": reason,
    }


def _response_to_json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise OpenRouterExtractionError("OpenRouter returned non-JSON response") from exc

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        logger.error(
            "openrouter_response_invalid_choices status=%s payload_keys=%s",
            response.status_code,
            list(payload.keys()) if isinstance(payload, dict) else [],
        )
        raise OpenRouterExtractionError("OpenRouter response had no choices")

    content = choices[0].get("message", {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        logger.error(
            "openrouter_response_empty_content status=%s first_choice_keys=%s",
            response.status_code,
            list(choices[0].keys()) if isinstance(choices[0], dict) else [],
        )
        raise OpenRouterExtractionError("OpenRouter response content was empty")

    try:
        decoded = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error(
            "openrouter_content_json_decode_failed status=%s content_preview=%s",
            response.status_code,
            _preview_text(content),
        )
        raise OpenRouterExtractionError("OpenRouter content was not valid JSON") from exc

    if not isinstance(decoded, dict):
        logger.error("openrouter_content_not_object decoded_type=%s", type(decoded).__name__)
        raise OpenRouterExtractionError("OpenRouter JSON payload must be an object")

    return decoded


def extract_with_openrouter(raw_text: str, config: OpenRouterConfig) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    request_payload: dict[str, Any] = {
        "model": config.model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": _build_messages(raw_text),
    }

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": config.app_url,
        "X-Title": config.app_name,
    }

    logger.info(
        "openrouter_extract_started model=%s timeout_seconds=%s max_retries=%s raw_text_chars=%s",
        config.model,
        config.timeout_seconds,
        config.max_retries,
        len(raw_text or ""),
    )

    last_error = ""
    for attempt in range(config.max_retries + 1):
        logger.info("openrouter_request_attempt model=%s attempt=%s", config.model, attempt + 1)
        try:
            response = requests.post(
                OPENROUTER_CHAT_URL,
                headers=headers,
                json=request_payload,
                timeout=config.timeout_seconds,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            logger.warning("openrouter_request_exception attempt=%s error=%s", attempt + 1, last_error)
            if attempt < config.max_retries:
                continue
            raise OpenRouterExtractionError(f"OpenRouter request failed: {last_error}") from exc

        if response.status_code >= 500 or response.status_code == 429:
            last_error = f"HTTP {response.status_code}"
            logger.warning("openrouter_retryable_status attempt=%s status=%s", attempt + 1, response.status_code)
            if attempt < config.max_retries:
                continue

        if response.status_code >= 400:
            logger.error("openrouter_non_retryable_status status=%s", response.status_code)
            raise OpenRouterExtractionError(f"OpenRouter returned HTTP {response.status_code}: {response.text[:300]}")

        try:
            raw_response = response.json()
        except ValueError as exc:
            logger.error(
                "openrouter_response_json_decode_failed status=%s body_preview=%s",
                response.status_code,
                _preview_text(response.text),
            )
            raise OpenRouterExtractionError("OpenRouter returned invalid JSON response envelope") from exc

        try:
            decoded = _response_to_json(response)
            validated = _validate_extraction_payload(decoded)
        except OpenRouterExtractionError:
            logger.exception(
                "openrouter_response_validation_failed status=%s model=%s body_preview=%s",
                response.status_code,
                config.model,
                _preview_text(response.text),
            )
            raise

        logger.info(
            "openrouter_extract_validated model=%s performers=%s works=%s has_venue=%s has_date=%s sold_out=%s price_tags=%s",
            config.model,
            len(validated.get("p", [])),
            len(validated.get("w", [])),
            bool(validated.get("v")),
            bool(validated.get("d")),
            bool(validated.get("s")),
            len(validated.get("pt", [])),
        )
        logger.info("openrouter_request_success model=%s", config.model)
        return validated, request_payload, raw_response

    raise OpenRouterExtractionError(f"OpenRouter retries exhausted: {last_error}")


def disambiguate_with_openrouter(
    entity_type: str,
    raw_text: str,
    candidates: list[dict[str, Any]],
    config: OpenRouterConfig,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    serialized_candidates = _serialize_disambiguation_candidates(candidates)[:8]
    if not serialized_candidates:
        raise OpenRouterDisambiguationError("No usable candidates were supplied for disambiguation")

    request_payload: dict[str, Any] = {
        "model": config.model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": _build_disambiguation_messages(entity_type, raw_text, serialized_candidates),
    }

    logger.info(
        "openrouter_disambiguation_started model=%s entity_type=%s raw_text_preview=%s candidate_count=%s",
        config.model,
        entity_type,
        _preview_text(raw_text),
        len(serialized_candidates),
    )

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": config.app_url,
        "X-Title": config.app_name,
    }

    last_error = ""
    valid_ids = {candidate["id"] for candidate in serialized_candidates}
    for attempt in range(config.max_retries + 1):
        logger.info(
            "openrouter_disambiguation_attempt model=%s attempt=%s entity_type=%s",
            config.model,
            attempt + 1,
            entity_type,
        )
        try:
            response = requests.post(
                OPENROUTER_CHAT_URL,
                headers=headers,
                json=request_payload,
                timeout=config.timeout_seconds,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            logger.warning("openrouter_disambiguation_exception attempt=%s error=%s", attempt + 1, last_error)
            if attempt < config.max_retries:
                continue
            raise OpenRouterDisambiguationError(f"OpenRouter disambiguation request failed: {last_error}") from exc

        if response.status_code >= 500 or response.status_code == 429:
            last_error = f"HTTP {response.status_code}"
            logger.warning(
                "openrouter_disambiguation_retryable_status attempt=%s status=%s",
                attempt + 1,
                response.status_code,
            )
            if attempt < config.max_retries:
                continue

        if response.status_code >= 400:
            logger.error("openrouter_disambiguation_non_retryable_status status=%s", response.status_code)
            raise OpenRouterDisambiguationError(
                f"OpenRouter disambiguation returned HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            raw_response = response.json()
        except ValueError as exc:
            logger.error(
                "openrouter_disambiguation_envelope_decode_failed status=%s body_preview=%s",
                response.status_code,
                _preview_text(response.text),
            )
            raise OpenRouterDisambiguationError("OpenRouter disambiguation returned invalid JSON envelope") from exc

        try:
            decoded = _response_to_json(response)
            validated = _validate_disambiguation_payload(decoded)
        except (OpenRouterExtractionError, OpenRouterDisambiguationError):
            logger.exception(
                "openrouter_disambiguation_validation_failed status=%s entity_type=%s body_preview=%s",
                response.status_code,
                entity_type,
                _preview_text(response.text),
            )
            raise

        selected_id = validated["id"]
        if selected_id is not None and selected_id not in valid_ids:
            logger.error(
                "openrouter_disambiguation_invalid_id entity_type=%s selected_id=%s valid_ids=%s",
                entity_type,
                selected_id,
                sorted(valid_ids),
            )
            raise OpenRouterDisambiguationError("Disambiguation selected a candidate id outside the provided list")

        logger.info(
            "openrouter_disambiguation_success model=%s entity_type=%s selected_id=%s confidence=%.2f",
            config.model,
            entity_type,
            selected_id,
            validated["confidence"],
        )
        return validated, request_payload, raw_response

    raise OpenRouterDisambiguationError(f"OpenRouter disambiguation retries exhausted: {last_error}")


def fallback_extract_from_flat_fields(record: dict[str, Any]) -> dict[str, Any]:
    logger.info("openrouter_fallback_extract_used")
    performers_raw = str(record.get("performers", "") or "")
    program_raw = str(record.get("program", "") or "")
    hall = str(record.get("hall", "") or "").strip()
    date_text = str(record.get("date_normalized", "") or record.get("date", "") or "").strip()
    source_text = "\n".join(
        [
            str(record.get("name", "") or ""),
            performers_raw,
            program_raw,
            hall,
        ]
    )

    performers = _as_string_list(
        [performers_raw],
        split_pattern=r"\n+|\s*\|\s*|\s*/\s*|\s*;\s*|\s*&\s*|\s+[Uu][Nn][Dd]\s+|\s+[Aa][Nn][Dd]\s+",
    )

    works: list[dict[str, str]] = []
    seen_work_titles: set[str] = set()
    for chunk in re.split(r"\n+|\s*\|\s*|\s*;\s*|\s*/\s*", program_raw):
        value = chunk.strip()
        if value:
            lowered = value.lower()
            if lowered in seen_work_titles:
                continue
            seen_work_titles.add(lowered)
            works.append({"c": "", "t": value})

    sold_out = bool(re.search(r"\bsold\s*-?\s*out\b|\bausverkauft\b", source_text, re.IGNORECASE))
    price_tags: list[str] = []
    seen_prices: set[str] = set()
    for match in re.findall(
        r"(?:\b(?:ab|from)\s+\d+[\d.,]*\s*(?:EUR|€|CHF|\$)\b|\b\d+[\d.,]*\s*(?:EUR|€|CHF|\$)\b|\bfree\b)",
        source_text,
        flags=re.IGNORECASE,
    ):
        normalized = re.sub(r"\s+", " ", match).strip()
        key = normalized.lower()
        if key in seen_prices:
            continue
        seen_prices.add(key)
        price_tags.append(normalized)

    return {
        "p": performers,
        "w": works,
        "v": hall,
        "d": date_text,
        "s": sold_out,
        "pt": price_tags,
    }
