# backend_api/app/services/phrase_service.py

# This file is responsible for:
# 1. storing the phrases you want to recognize
# 2. normalizing text before comparison
# 3. comparing the transcript against phrase aliases
# 4. returning information about the best-matching phrase clip

import re
from pathlib import Path

# RapidFuzz is better than Python's basic SequenceMatcher for fuzzy text matching.
# It gives scores from 0 to 100 and has helpers like partial_ratio and token_set_ratio.
from rapidfuzz import fuzz

# This points to the folder where your real phrase audio clips live.
PHRASE_CLIPS_DIR = Path(__file__).resolve().parent.parent.parent / "phrase_clips"
PHRASE_CLIPS_DIR.mkdir(exist_ok=True)

# IMPORTANT:
# Add multiple aliases for the SAME phrase.
# Why?
# Because Whisper may return:
# - Devanagari Nepali
# - Romanized Nepali
# - slightly different spellings
#
# The more realistic aliases you add, the better your matching becomes.
PHRASE_LIBRARY = [
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

    # Example for adding another phrase later:
    # {
    #     "id": "phrase_2",
    #     "aliases": [
    #         "त्यसो गर्यो भने कस्तो होला",
    #         "teso garyo vane kasto hola",
    #         "tesho garyo vane kasho hola"
    #     ],
    #     "clip_filename": "teshoGaryoVaneKashoHola.m4a"
    # }
]


def normalize_text(text: str) -> str:
    """
    Make text easier to compare.

    What this does:
    - lowercase the text
    - remove punctuation
    - collapse repeated spaces

    Example:
    "Tesho-Gare, Kasho Hola!" -> "tesho gare kasho hola"
    """
    cleaned_text = text.lower().strip()
    cleaned_text = re.sub(r"[^\w\s]", " ", cleaned_text, flags=re.UNICODE)
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
    return cleaned_text


def build_clip_url(clip_filename: str) -> str:
    """
    Convert a clip file name into the public backend URL.

    Example:
    teshoGareKashoHola1.m4a
    ->
    /phrase-clips/teshoGareKashoHola1.m4a
    """
    return f"/phrase-clips/{clip_filename}"


def score_transcript_against_alias(transcript: str, alias: str) -> float:
    """
    Compare one transcript against one alias using multiple fuzzy strategies.

    Why multiple strategies?
    - ratio: good when strings are close overall
    - partial_ratio: good when one string is inside another
    - token_set_ratio: good when extra words are present

    We keep the best score.
    """
    normalized_transcript = normalize_text(transcript)
    normalized_alias = normalize_text(alias)

    # Perfect containment match
    if normalized_alias and normalized_alias in normalized_transcript:
        return 100.0

    return max(
        fuzz.ratio(normalized_transcript, normalized_alias),
        fuzz.partial_ratio(normalized_transcript, normalized_alias),
        fuzz.token_set_ratio(normalized_transcript, normalized_alias),
    )


def find_best_phrase_match(transcript: str, minimum_score: float = 70.0):
    """
    Find the best matching phrase from the phrase library.

    Returns:
    - matched: True/False
    - matched_phrase: the phrase dict that matched best
    - matched_alias: the exact alias that scored highest
    - score: numeric score
    - clip_exists: whether the real audio file exists on disk
    - clip_url: public URL for the clip if it exists
    """
    normalized_transcript = normalize_text(transcript)

    # If transcript is empty, there is nothing to match.
    if not normalized_transcript:
        return {
            "matched": False,
            "matched_phrase": None,
            "matched_alias": None,
            "score": 0.0,
            "clip_exists": False,
            "clip_url": None
        }

    best_phrase = None
    best_alias = None
    best_score = 0.0

    # Compare transcript against every alias of every phrase.
    for phrase in PHRASE_LIBRARY:
        for alias in phrase["aliases"]:
            score = score_transcript_against_alias(normalized_transcript, alias)

            if score > best_score:
                best_score = score
                best_phrase = phrase
                best_alias = alias

    clip_exists = False
    clip_url = None

    # If a best phrase was found, check if the clip file is really present.
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