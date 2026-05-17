# backend_api/app/services/phrase_service.py

# This file is responsible for:
# 1. loading the phrase list
# 2. normalizing transcript text
# 3. handling known confusing Nepali spellings/sounds
# 4. fuzzy-matching transcript text against phrase aliases
# 5. returning clip metadata for the best phrase match

import json
import re
from pathlib import Path

from rapidfuzz import fuzz

# Folder where your real phrase audio clips live
PHRASE_CLIPS_DIR = Path(__file__).resolve().parent.parent.parent / "phrase_clips"
PHRASE_CLIPS_DIR.mkdir(exist_ok=True)

# Optional JSON file path.
# If this file exists, we will load phrases from it.
# If it does not exist, we will fall back to DEFAULT_PHRASE_LIBRARY below.
PHRASES_JSON_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "phrases.json"

# Fallback phrase data.
# This is used only if phrases.json does not exist.
DEFAULT_PHRASE_LIBRARY = [
    {
        "id": "phrase_1",
        "aliases": [
            "त्यसो गरे कस्तो होला",
            "तेसो गरे कसो होला",
            "teso gare kasto hola",
            "tesho gare kasho hola",
            "tesho gare kaso hola"
        ],
        "clip_filename": "teshoGareKashoHola1.m4a"
    },
    {
        "id": "phrase_2",
        "aliases": [
            "आबुई आबुई",
            "आबुई, आबुई",
            "अभुई अभुई",
            "अभुई, अभुई",
            "abuii abuii",
            "abui abui"
        ],
        "clip_filename": "abuiiiAbuiii.m4a"
    }
]

# This map is the practical fix for confusing word forms.
# Idea:
# convert known near-equivalent spellings into one common internal form.
#
# You can grow this list over time whenever you see repeated transcription mistakes.
CONFUSION_REPLACEMENTS = {
    "आबुई": "ABUI",
    "अभुई": "ABUI",
    "अबुई": "ABUI",
    "abuii": "ABUI",
    "abui": "ABUI",
}


def load_phrase_library():
    """
    Load phrase data.

    Priority:
    1. If data/phrases.json exists, use it
    2. Otherwise use the fallback list inside this file
    """
    if PHRASES_JSON_PATH.exists():
        with PHRASES_JSON_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError("phrases.json must contain a JSON array (list of phrase objects).")

        return data

    return DEFAULT_PHRASE_LIBRARY


def validate_phrase_record(phrase: dict):
    """
    Validate one phrase record.

    Every phrase must have:
    - id
    - aliases
    - clip_filename
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

    Example:
    - आबुई -> ABUI
    - अभुई -> ABUI

    This is the easiest practical fix for your current problem.
    It is not a full Nepali phonetic engine, but it works well
    for repeated words/phrases you care about.
    """
    normalized = text

    for source_text, replacement_text in CONFUSION_REPLACEMENTS.items():
        normalized = normalized.replace(source_text.lower(), replacement_text.lower())

    return normalized


def build_clip_url(clip_filename: str) -> str:
    """
    Convert a clip filename into a public backend URL.
    """
    return f"/phrase-clips/{clip_filename}"


def score_transcript_against_alias(transcript: str, alias: str) -> float:
    """
    Compare one transcript against one alias.

    We score two versions:
    1. normal cleaned text
    2. confusion-normalized text

    Then we keep the better score.
    """
    # Normal cleaned forms
    normalized_transcript = normalize_text(transcript)
    normalized_alias = normalize_text(alias)

    # Confusion-normalized forms
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


def get_phrase_debug_scores(transcript: str):
    """
    Return debugging scores for every phrase.

    This is useful when you want to know:
    - what the best phrase was
    - which alias scored highest
    - how close other phrases were
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

    results.sort(key=lambda item: item["best_score"], reverse=True)
    return results


def find_best_phrase_match(transcript: str, minimum_score: float = 70.0):
    """
    Return the best phrase match for the transcript.
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