import re
from difflib import SequenceMatcher

PHRASE_LIBRARY = [
    {
        "id": "phrase_1",
        "phrase_text": "tesho-gare kasho hola",
        "clip_filename": "teshoGareKashoHola1.m4a"
    }
    # {
    #     "id": "phrase_5",
    #     "phrase_text": "tesho-garyo vane kasho hola",
    #     "clip_filename": "teshoGaryoVaneKashoHola.m4a"
    # }
]


def normalize_text(text: str) -> str:
    cleaned_text = text.lower().strip()
    cleaned_text = re.sub(r"[^\w\s]", " ", cleaned_text, flags=re.UNICODE)
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
    return cleaned_text


def find_best_phrase_match(transcript: str, minimum_score: float = 0.75):
    normalized_transcript = normalize_text(transcript)

    if not normalized_transcript:
        return {
            "matched": False,
            "matched_phrase": None,
            "score": 0.0
        }

    best_phrase = None
    best_score = 0.0

    for phrase in PHRASE_LIBRARY:
        normalized_phrase = normalize_text(phrase["phrase_text"])

        if normalized_phrase in normalized_transcript:
            score = 1.0
        else:
            score = SequenceMatcher(None, normalized_transcript, normalized_phrase).ratio()

        if score > best_score:
            best_score = score
            best_phrase = phrase

    if best_phrase and best_score >= minimum_score:
        return {
            "matched": True,
            "matched_phrase": best_phrase,
            "score": round(best_score, 3)
        }

    return {
        "matched": False,
        "matched_phrase": best_phrase,
        "score": round(best_score, 3)
    }