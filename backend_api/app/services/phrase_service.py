# backend_api/app/services/phrase_service.py
#
# This file is responsible for phrase matching only.
#
# What this file does:
# 1. Load phrase data from backend_api/data/phrases.json
# 2. Normalize transcript text and aliases
# 3. Check whether the transcript contains any known alias
# 4. Return matched clip metadata if an alias is found
# 5. Return one simple score number for visibility
#
# What this file intentionally does NOT do anymore:
# - no minimum_score
# - no used_minimum_score
# - no debug_scores
# - no threshold-based decision
# - no OpenAI fallback decision
#
# Phrase matching is still kept because it powers:
# - matchedClip response
# - Play Match Clip button in Angular
#
# Phase 3A improvement:
# This version improves matching by normalizing common Nepali/roman variants.
# It still keeps the matching rule simple:
# - if a normalized alias is contained in the normalized transcript, return a match
# - otherwise matchedClip is null
#
# The score is still display-only. It does not decide fallback.

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

# backend_api folder
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

# Folder where real phrase clips live:
# backend_api/phrase_clips
PHRASE_CLIPS_DIR = BACKEND_ROOT / "phrase_clips"
PHRASE_CLIPS_DIR.mkdir(parents=True, exist_ok=True)

# JSON file containing phrase aliases:
# backend_api/data/phrases.json
PHRASES_JSON_PATH = BACKEND_ROOT / "data" / "phrases.json"


# Known word replacements.
#
# Beginner explanation:
# Speech-to-text may write the same sound in different ways.
# For example:
# - अभुई
# - आबुई
# - abui
# - abhui
#
# For phrase matching, we convert those variations into one internal word:
# ABUI
#
# This is not full translation or transliteration.
# It is just a small project-specific normalization dictionary.
KNOWN_WORD_REPLACEMENTS = {
    # अभुई / आबुई phrase variants
    "आबुई": "ABUI",
    "आबुइ": "ABUI",
    "अभुई": "ABUI",
    "अभुइ": "ABUI",
    "अबुई": "ABUI",
    "अबुइ": "ABUI",
    "abuii": "ABUI",
    "abui": "ABUI",
    "abhui": "ABUI",
    "abhuii": "ABUI",

    # त्यसो / तेसो variants
    "त्यसो": "TESO",
    "तेसो": "TESO",
    "teso": "TESO",
    "tesho": "TESO",
    "tyaso": "TESO",
    "tesso": "TESO",

    # गरे variants
    "गरे": "GARE",
    "गरें": "GARE",
    "gare": "GARE",
    "garey": "GARE",

    # कस्तो / काशो variants
    "कस्तो": "KASTO",
    "कस्तोे": "KASTO",
    "काशो": "KASTO",
    "कसो": "KASTO",
    "kasto": "KASTO",
    "kasho": "KASTO",
    "kaso": "KASTO",

    # होला variants
    "होला": "HOLA",
    "hola": "HOLA",
    "holaa": "HOLA",
}


def load_phrase_library() -> list[dict[str, Any]]:
    """
    Load phrase data from data/phrases.json.

    Returns:
        A Python list of phrase objects.

    Java comparison:
        This is similar to reading a JSON config file into a List<Map<String, Object>>.
    """
    if not PHRASES_JSON_PATH.exists():
        return []

    with PHRASES_JSON_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("phrases.json must contain a JSON array/list.")

    return data


def get_phrase_field(
    phrase: dict[str, Any],
    camel_name: str,
    snake_name: str | None = None,
    default_value: Any = None,
) -> Any:
    """
    Support both camelCase and snake_case phrase JSON fields.

    Example:
    - clipFileName
    - clip_filename

    This protects you while you are refactoring.
    """
    if camel_name in phrase:
        return phrase[camel_name]

    if snake_name and snake_name in phrase:
        return phrase[snake_name]

    return default_value


def validate_phrase_record(phrase: dict[str, Any]) -> None:
    """
    Validate one phrase record.

    Required:
    - id
    - aliases
    - clipFileName or clip_filename

    Optional:
    - displayName or display_name
    """
    if not isinstance(phrase, dict):
        raise ValueError("Each phrase entry must be a JSON object.")

    phrase_id = phrase.get("id")

    if not phrase_id:
        raise ValueError("Each phrase must have an 'id' field.")

    aliases = phrase.get("aliases")

    if not isinstance(aliases, list) or len(aliases) == 0:
        raise ValueError(f"Phrase '{phrase_id}' must have a non-empty aliases list.")

    clip_file_name = get_phrase_field(
        phrase,
        camel_name="clipFileName",
        snake_name="clip_filename",
    )

    if not clip_file_name:
        raise ValueError(
            f"Phrase '{phrase_id}' is missing 'clipFileName' or 'clip_filename'."
        )


def remove_invisible_characters(text: str) -> str:
    """
    Remove invisible characters that commonly cause string matching problems.

    Example:
    Sometimes text can look like:
        अभुई अभुई

    but secretly contain zero-width characters.
    That makes direct string matching fail.

    This function removes those hidden characters.
    """
    return re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text or "")


def normalize_text(text: str) -> str:
    """
    Light text normalization.

    This does:
    - Unicode normalization
    - remove invisible characters
    - lowercase
    - replace Nepali danda punctuation with spaces
    - remove punctuation
    - collapse repeated spaces

    This is not heavy Nepali NLP.
    It is just enough for the current phrase matching milestone.
    """
    cleaned_text = text or ""

    # Normalize Unicode so visually similar text has a better chance to compare equal.
    cleaned_text = unicodedata.normalize("NFKC", cleaned_text)

    # Remove hidden characters.
    cleaned_text = remove_invisible_characters(cleaned_text)

    # Lowercase helps romanized aliases like ABUI / abui / Abui.
    cleaned_text = cleaned_text.lower().strip()

    # Nepali danda marks are sentence punctuation.
    cleaned_text = cleaned_text.replace("।", " ")
    cleaned_text = cleaned_text.replace("॥", " ")

    # Remove punctuation but keep letters/numbers/spaces in all languages.
    cleaned_text = re.sub(r"[^\w\s]", " ", cleaned_text, flags=re.UNICODE)

    # Collapse extra spaces.
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()

    return cleaned_text


def apply_known_word_normalization(text: str) -> str:
    """
    Replace known Nepali/roman variants with one canonical internal token.

    Example:
        अभुई अभुई -> ABUI ABUI
        abui abui -> ABUI ABUI

    This makes matching more stable.
    """
    normalized = normalize_text(text)

    # We split by space so replacements happen word-by-word.
    # This avoids replacing letters inside unrelated words.
    words = normalized.split()
    converted_words: list[str] = []

    for word in words:
        converted_words.append(KNOWN_WORD_REPLACEMENTS.get(word, word))

    return " ".join(converted_words)


def build_clip_url(clip_file_name: str) -> str:
    """
    Convert a clip filename into the public backend URL.

    Example:
    abuiiiAbuiii.m4a -> /phrase-clips/abuiiiAbuiii.m4a
    """
    return f"/phrase-clips/{clip_file_name}"


def alias_is_contained_in_transcript(transcript: str, alias: str) -> bool:
    """
    The simplified phrase matching rule.

    A phrase matches when:
    1. the normalized alias is contained in the normalized transcript, OR
    2. the known-word-normalized alias is contained in the known-word-normalized transcript

    This avoids threshold/minimum-score confusion.
    """
    normalized_transcript = normalize_text(transcript)
    normalized_alias = normalize_text(alias)

    if not normalized_transcript or not normalized_alias:
        return False

    if normalized_alias in normalized_transcript:
        return True

    canonical_transcript = apply_known_word_normalization(transcript)
    canonical_alias = apply_known_word_normalization(alias)

    if not canonical_transcript or not canonical_alias:
        return False

    return canonical_alias in canonical_transcript


def score_transcript_against_alias(transcript: str, alias: str) -> float:
    """
    Return one simple score number for visibility.

    Important:
    This score is NOT used for fallback.
    This score is NOT checked against a minimum threshold.
    This score does NOT decide whether to call OpenAI.

    Match decision is simple:
    - alias contained in transcript -> matchedClip
    - otherwise -> matchedClip null
    """
    normalized_transcript = normalize_text(transcript)
    normalized_alias = normalize_text(alias)

    if not normalized_transcript or not normalized_alias:
        return 0.0

    canonical_transcript = apply_known_word_normalization(transcript)
    canonical_alias = apply_known_word_normalization(alias)

    direct_normal_match = 100.0 if normalized_alias in normalized_transcript else 0.0
    direct_canonical_match = 100.0 if canonical_alias in canonical_transcript else 0.0

    normal_score = max(
        fuzz.ratio(normalized_transcript, normalized_alias),
        fuzz.partial_ratio(normalized_transcript, normalized_alias),
        fuzz.token_set_ratio(normalized_transcript, normalized_alias),
    )

    canonical_score = max(
        fuzz.ratio(canonical_transcript, canonical_alias),
        fuzz.partial_ratio(canonical_transcript, canonical_alias),
        fuzz.token_set_ratio(canonical_transcript, canonical_alias),
    )

    return float(
        max(
            direct_normal_match,
            direct_canonical_match,
            normal_score,
            canonical_score,
        )
    )


def build_matched_clip_response(
    phrase: dict[str, Any],
    matched_alias: str,
) -> dict[str, Any]:
    """
    Build the matchedClip object returned to Angular.
    """
    phrase_id = phrase["id"]

    display_name = get_phrase_field(
        phrase,
        camel_name="displayName",
        snake_name="display_name",
        default_value=matched_alias,
    )

    clip_file_name = get_phrase_field(
        phrase,
        camel_name="clipFileName",
        snake_name="clip_filename",
    )

    clip_path = PHRASE_CLIPS_DIR / clip_file_name
    clip_exists = clip_path.exists()

    return {
        "id": phrase_id,
        "displayName": display_name,
        "matchedAlias": matched_alias,
        "clipFileName": clip_file_name,
        "clipExists": clip_exists,
        "clipUrl": build_clip_url(clip_file_name) if clip_exists else None,
    }


def find_phrase_match(transcript: str) -> dict[str, Any]:
    """
    Find a phrase match for a transcript.

    Returns:
    {
        "score": 100.0,
        "matchedClip": {...} or None
    }

    Why score still exists:
    You asked to remove the scoring mechanism used for fallback/debug/minimum
    threshold decisions. But you also asked to show matched score.
    So this function returns one simple best score for visibility only.
    """
    phrase_library = load_phrase_library()

    best_score = 0.0
    first_contained_match: tuple[dict[str, Any], str] | None = None

    for phrase in phrase_library:
        validate_phrase_record(phrase)

        for alias in phrase["aliases"]:
            score = score_transcript_against_alias(transcript, alias)

            if score > best_score:
                best_score = score

            if first_contained_match is None and alias_is_contained_in_transcript(
                transcript,
                alias,
            ):
                first_contained_match = (phrase, alias)

    matched_clip = None

    if first_contained_match is not None:
        matched_phrase, matched_alias = first_contained_match
        matched_clip = build_matched_clip_response(
            phrase=matched_phrase,
            matched_alias=matched_alias,
        )

    return {
        "score": round(best_score, 2),
        "matchedClip": matched_clip,
    }


def get_devanagari_alias_hints(max_aliases: int = 12) -> list[str]:
    """
    Return a small list of Devanagari aliases for OpenAI transcription prompt.

    Why this exists:
    A transcription model can do better if we give it hints about uncommon
    phrase spellings/names it may hear.
    """
    phrase_library = load_phrase_library()

    seen = set()
    hints: list[str] = []

    for phrase in phrase_library:
        validate_phrase_record(phrase)

        for alias in phrase["aliases"]:
            cleaned_alias = str(alias).strip()

            # Keep only aliases that contain Devanagari characters.
            if re.search(r"[\u0900-\u097F]", cleaned_alias):
                if cleaned_alias not in seen:
                    seen.add(cleaned_alias)
                    hints.append(cleaned_alias)

                if len(hints) >= max_aliases:
                    return hints

    return hints