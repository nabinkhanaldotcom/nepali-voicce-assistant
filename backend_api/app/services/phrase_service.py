# backend_api/app/services/phrase_service.py

# This file is responsible for:
# 1. loading phrase data from JSON
# 2. normalizing text before comparison
# 3. handling known confusing Nepali spellings/sounds
# 4. fuzzy-matching transcript text against phrase aliases
# 5. supporting phrase-specific thresholds
# 6. returning clip metadata for the best phrase match
# 7. giving OpenAI a small list of Nepali phrase hints

import json
import re
from pathlib import Path

from rapidfuzz import fuzz

# Folder where real phrase clips live
PHRASE_CLIPS_DIR = Path(__file__).resolve().parent.parent.parent / "phrase_clips"
PHRASE_CLIPS_DIR.mkdir(exist_ok=True)

# JSON file containing phrase data
PHRASES_JSON_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "phrases.json"

# Known confusion replacements.
# This is a practical rule-based helper for repeated word-form confusion.
CONFUSION_REPLACEMENTS = {
    "आबुई": "ABUI",
    "अभुई": "ABUI",
    "अबुई": "ABUI",
    "abuii": "ABUI",
    "abui": "ABUI",
}


def load_phrase_library():
    """
    Load phrase data from data/phrases.json.

    Returns:
        A Python list of phrase objects.
    """
    if not PHRASES_JSON_PATH.exists():
        return []

    with PHRASES_JSON_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("phrases.json must contain a JSON array (list of phrase objects).")

    return data


def validate_phrase_record(phrase: dict):
    """
    Validate one phrase record.

    Required fields:
    - id
    - aliases
    - clip_filename

    Optional:
    - minimum_score
    """
    if not isinstance(phrase, dict):
        raise ValueError("Each phrase entry must be a JSON object.")

    if "id" not in phrase:
        raise ValueError("Each phrase must have an 'id' field.")

    if "aliases" not in phrase:
        raise ValueError(f"Phrase '{phrase.get('id', 'unknown')}' is missing 'aliases'.")

    if "clip_filename" not in phrase:
        raise ValueError(f"Phrase '{phrase.get('id', 'unknown')}' is missing 'clip_filename'.")

    if not isinstance(phrase["aliases"], list) or len(phrase["aliases"]) == 0:
        raise ValueError(f"Phrase '{phrase.get('id', 'unknown')}' must have a non-empty 'aliases' list.")

    if "minimum_score" in phrase and not isinstance(phrase["minimum_score"], (int, float)):
        raise ValueError(f"Phrase '{phrase.get('id', 'unknown')}' has invalid 'minimum_score'.")


def normalize_text(text: str) -> str:
    """
    Basic text normalization.

    This does:
    - lowercase
    - remove punctuation
    - collapse repeated spaces
    """
    cleaned_text = text.lower().strip()
    cleaned_text = re.sub(r"[^\w\s]", " ", cleaned_text, flags=re.UNICODE)
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
    return cleaned_text


def apply_confusion_normalization(text: str) -> str:
    """
    Replace known confusing spellings with one internal canonical form.
    """
    normalized = text

    for source_text, replacement_text in CONFUSION_REPLACEMENTS.items():
        normalized = normalized.replace(source_text.lower(), replacement_text.lower())

    return normalized


def build_clip_url(clip_filename: str) -> str:
    """
    Convert a clip filename into the public backend URL.
    """
    return f"/phrase-clips/{clip_filename}"


def get_phrase_minimum_score(phrase: dict, default_minimum_score: float) -> float:
    """
    Return the threshold to use for one phrase.

    If the phrase defines its own minimum_score, use that.
    Otherwise use the default threshold.
    """
    if "minimum_score" in phrase:
        return float(phrase["minimum_score"])

    return float(default_minimum_score)


def score_transcript_against_alias(transcript: str, alias: str) -> float:
    """
    Compare one transcript against one alias.

    We score:
    1. normal cleaned text
    2. confusion-normalized text

    Then we keep the best score.
    """
    normalized_transcript = normalize_text(transcript)
    normalized_alias = normalize_text(alias)

    confusion_transcript = apply_confusion_normalization(normalized_transcript)
    confusion_alias = apply_confusion_normalization(normalized_alias)

    # Direct containment match on normal text
    direct_normal_match = 100.0 if normalized_alias and normalized_alias in normalized_transcript else 0.0

    # Direct containment match on confusion-normalized text
    direct_confusion_match = 100.0 if confusion_alias and confusion_alias in confusion_transcript else 0.0

    # Fuzzy scoring on normal text
    normal_score = max(
        fuzz.ratio(normalized_transcript, normalized_alias),
        fuzz.partial_ratio(normalized_transcript, normalized_alias),
        fuzz.token_set_ratio(normalized_transcript, normalized_alias),
    )

    # Fuzzy scoring on confusion-normalized text
    confusion_score = max(
        fuzz.ratio(confusion_transcript, confusion_alias),
        fuzz.partial_ratio(confusion_transcript, confusion_alias),
        fuzz.token_set_ratio(confusion_transcript, confusion_alias),
    )

    return max(
        direct_normal_match,
        direct_confusion_match,
        normal_score,
        confusion_score,
    )


def get_devanagari_alias_hints(max_aliases: int = 12):
    """
    Return a small list of Devanagari aliases.

    Why this exists:
    We can use these as hints in the OpenAI transcription prompt.
    OpenAI's docs say prompts can improve quality and help with specific words.
    """
    phrase_library = load_phrase_library()

    seen = set()
    hints = []

    for phrase in phrase_library:
        validate_phrase_record(phrase)

        for alias in phrase["aliases"]:
            cleaned_alias = alias.strip()

            # Keep only aliases that actually contain Devanagari characters
            if re.search(r"[\u0900-\u097F]", cleaned_alias):
                if cleaned_alias not in seen:
                    seen.add(cleaned_alias)
                    hints.append(cleaned_alias)

            if len(hints) >= max_aliases:
                return hints

    return hints


def get_phrase_debug_scores(transcript: str, default_minimum_score: float = 70.0):
    """
    Return debug scoring details for every phrase.
    """
    normalized_transcript = normalize_text(transcript)

    if not normalized_transcript:
        return []

    phrase_library = load_phrase_library()
    results = []

    for phrase in phrase_library:
        validate_phrase_record(phrase)

        best_alias = None
        best_score = 0.0
        alias_scores = []

        for alias in phrase["aliases"]:
            score = score_transcript_against_alias(normalized_transcript, alias)

            alias_scores.append({
                "alias": alias,
                "score": round(score, 2)
            })

            if score > best_score:
                best_score = score
                best_alias = alias

        phrase_minimum_score = get_phrase_minimum_score(phrase, default_minimum_score)

        clip_path = PHRASE_CLIPS_DIR / phrase["clip_filename"]
        clip_exists = clip_path.exists()
        clip_url = build_clip_url(phrase["clip_filename"]) if clip_exists else None

        alias_scores.sort(key=lambda item: item["score"], reverse=True)

        results.append({
            "phrase_id": phrase["id"],
            "clip_filename": phrase["clip_filename"],
            "best_alias": best_alias,
            "best_score": round(best_score, 2),
            "phrase_minimum_score": round(phrase_minimum_score, 2),
            "passes_phrase_threshold": best_score >= phrase_minimum_score,
            "clip_exists": clip_exists,
            "clip_url": clip_url,
            "alias_scores": alias_scores
        })

    results.sort(key=lambda item: item["best_score"], reverse=True)
    return results


def find_best_phrase_match(transcript: str, default_minimum_score: float = 70.0):
    """
    Find the best phrase match for a transcript.

    IMPORTANT:
    The best phrase is selected by highest score.
    Then that phrase is checked against its own threshold.
    """
    normalized_transcript = normalize_text(transcript)

    if not normalized_transcript:
        return {
            "matched": False,
            "matched_phrase": None,
            "matched_alias": None,
            "score": 0.0,
            "used_minimum_score": round(default_minimum_score, 2),
            "clip_exists": False,
            "clip_url": None
        }

    phrase_library = load_phrase_library()

    best_phrase = None
    best_alias = None
    best_score = 0.0

    for phrase in phrase_library:
        validate_phrase_record(phrase)

        for alias in phrase["aliases"]:
            score = score_transcript_against_alias(normalized_transcript, alias)

            if score > best_score:
                best_score = score
                best_phrase = phrase
                best_alias = alias

    clip_exists = False
    clip_url = None
    used_minimum_score = float(default_minimum_score)

    if best_phrase:
        used_minimum_score = get_phrase_minimum_score(best_phrase, default_minimum_score)

        clip_path = PHRASE_CLIPS_DIR / best_phrase["clip_filename"]
        clip_exists = clip_path.exists()
        clip_url = build_clip_url(best_phrase["clip_filename"]) if clip_exists else None

    return {
        "matched": best_phrase is not None and best_score >= used_minimum_score,
        "matched_phrase": best_phrase,
        "matched_alias": best_alias,
        "score": round(best_score, 2),
        "used_minimum_score": round(used_minimum_score, 2),
        "clip_exists": clip_exists,
        "clip_url": clip_url
    }