# backend_api/app/services/phrase_service.py

# This file is responsible for:
# 1. loading phrase data from JSON
# 2. normalizing text before comparison
# 3. scoring transcript against phrase aliases
# 4. finding the best match
# 5. returning debug score details for all phrases

import json
import re
from pathlib import Path
from rapidfuzz import fuzz

# Folder where real phrase audio clips live
PHRASE_CLIPS_DIR = Path(__file__).resolve().parent.parent.parent / "phrase_clips"
PHRASE_CLIPS_DIR.mkdir(exist_ok=True)

# JSON file that stores phrase definitions
PHRASES_JSON_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "phrases.json"


def load_phrase_library():
    """
    Load phrase definitions from the JSON file.

    Returns:
        A list of phrase objects.
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
    Validate that each phrase record has the required fields.
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


def normalize_text(text: str) -> str:
    """
    Normalize text before comparison.

    Example:
    "Tesho-Gare, Kasho Hola!" -> "tesho gare kasho hola"
    """
    cleaned_text = text.lower().strip()
    cleaned_text = re.sub(r"[^\w\s]", " ", cleaned_text, flags=re.UNICODE)
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
    return cleaned_text


def build_clip_url(clip_filename: str) -> str:
    """
    Convert a clip file name into a public backend URL.
    """
    return f"/phrase-clips/{clip_filename}"


def score_transcript_against_alias(transcript: str, alias: str) -> float:
    """
    Compare one transcript against one alias.

    We use several fuzzy matching strategies and keep the best score.
    Scores are from 0 to 100.
    """
    normalized_transcript = normalize_text(transcript)
    normalized_alias = normalize_text(alias)

    # Strong direct containment match
    if normalized_alias and normalized_alias in normalized_transcript:
        return 100.0

    return max(
        fuzz.ratio(normalized_transcript, normalized_alias),
        fuzz.partial_ratio(normalized_transcript, normalized_alias),
        fuzz.token_set_ratio(normalized_transcript, normalized_alias),
    )


def get_phrase_debug_scores(transcript: str):
    """
    Return score details for ALL phrases.

    This is useful when you want to understand:
    - which phrase came closest
    - which alias scored best
    - whether the clip exists
    - whether your threshold might be too high
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

        clip_path = PHRASE_CLIPS_DIR / phrase["clip_filename"]
        clip_exists = clip_path.exists()
        clip_url = build_clip_url(phrase["clip_filename"]) if clip_exists else None

        # Sort alias scores highest first so the best alias is easy to inspect
        alias_scores.sort(key=lambda item: item["score"], reverse=True)

        results.append({
            "phrase_id": phrase["id"],
            "clip_filename": phrase["clip_filename"],
            "best_alias": best_alias,
            "best_score": round(best_score, 2),
            "clip_exists": clip_exists,
            "clip_url": clip_url,
            "alias_scores": alias_scores
        })

    # Sort phrases by best score descending so the best candidate comes first
    results.sort(key=lambda item: item["best_score"], reverse=True)
    return results


def find_best_phrase_match(transcript: str, minimum_score: float = 70.0):
    """
    Find the best phrase match for a transcript.

    Returns:
    - matched: whether the score passed the threshold
    - matched_phrase: the phrase object that matched best
    - matched_alias: the alias that scored highest
    - score: the best score
    - clip_exists: whether the clip file exists
    - clip_url: public URL for the clip if it exists
    """
    normalized_transcript = normalize_text(transcript)

    if not normalized_transcript:
        return {
            "matched": False,
            "matched_phrase": None,
            "matched_alias": None,
            "score": 0.0,
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

    if best_phrase:
        clip_path = PHRASE_CLIPS_DIR / best_phrase["clip_filename"]
        clip_exists = clip_path.exists()
        clip_url = build_clip_url(best_phrase["clip_filename"]) if clip_exists else None

    return {
        "matched": best_phrase is not None and best_score >= minimum_score,
        "matched_phrase": best_phrase,
        "matched_alias": best_alias,
        "score": round(best_score, 2),
        "clip_exists": clip_exists,
        "clip_url": clip_url
    }