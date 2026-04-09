from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from unidecode import unidecode


FORM_KEYWORDS = (
    "sonata",
    "ballade",
    "symphony",
    "sinfonie",
    "concerto",
    "konzert",
    "suite",
    "requiem",
    "etude",
    "prelude",
    "fugue",
)


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    lowered = normalized.lower()
    lowered = re.sub(r"[^\w\s.-]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def detect_script(value: str) -> str:
    if re.search(r"[\uac00-\ud7a3]", value or ""):
        return "hangul"
    if re.search(r"[A-Za-z]", value or ""):
        return "latin"
    if re.search(r"[\u0400-\u04FF]", value or ""):
        return "cyrillic"
    return "unknown"


def transliterate_text(value: str) -> str:
    transliterated = unidecode(value or "")
    return normalize_text(transliterated)


def performer_variants(name: str) -> tuple[str, list[str], str]:
    script = detect_script(name)
    base = normalize_text(name)
    transliterated = transliterate_text(name)

    variants: list[str] = []
    for value in [base, transliterated]:
        value = value.strip()
        if value and value not in variants:
            variants.append(value)

    primary = variants[0] if variants else ""
    tokens = primary.split()
    if len(tokens) >= 2:
        swapped = " ".join([tokens[-1], *tokens[:-1]])
        if swapped not in variants:
            variants.append(swapped)

    return primary, variants, script


@dataclass
class WorkNormalized:
    composer: str
    composer_normalized: str
    title: str
    title_normalized: str
    form: str
    number: int | None
    opus: str
    key: str


def normalize_work(composer: str, title: str) -> WorkNormalized:
    composer_clean = (composer or "").strip()
    title_clean = (title or "").strip()
    title_normalized = normalize_text(title_clean)

    form = ""
    for keyword in FORM_KEYWORDS:
        if keyword in title_normalized:
            form = keyword
            break

    number_match = re.search(r"(?:nr\.?|no\.?|number)\s*(\d+)", title_normalized)
    number = int(number_match.group(1)) if number_match else None

    opus_match = re.search(r"(?:op\.?|opus)\s*(\d+[a-z]?)", title_normalized)
    opus = opus_match.group(1) if opus_match else ""

    key_match = re.search(r"\b([a-g])\s*[- ]?(major|minor|dur|moll)\b", title_normalized)
    key = ""
    if key_match:
        tonic = key_match.group(1)
        quality = key_match.group(2)
        if quality == "dur":
            quality = "major"
        elif quality == "moll":
            quality = "minor"
        key = f"{tonic} {quality}"

    return WorkNormalized(
        composer=composer_clean,
        composer_normalized=normalize_text(composer_clean),
        title=title_clean,
        title_normalized=title_normalized,
        form=form,
        number=number,
        opus=opus,
        key=key,
    )


def normalize_venue(value: str) -> str:
    normalized = normalize_text(value)
    normalized = normalized.replace(" gross", " gros")
    return normalized.strip()
