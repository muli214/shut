import re
import unicodedata


QUESTION_WORDS = {
    "האם",
    "מותר",
    "אסור",
    "אפשר",
    "צריך",
    "שאלה",
    "הרב",
    "מה",
    "למה",
    "מתי",
    "איך",
    "איפה",
    "מי",
}

COMMON_TOKENS = QUESTION_WORDS | {
    "של",
    "על",
    "עם",
    "זה",
    "זאת",
    "או",
    "אם",
    "גם",
    "אבל",
    "כי",
    "רק",
    "כל",
    "יש",
    "אין",
    "אני",
    "אנחנו",
    "הוא",
    "היא",
    "הם",
    "הן",
    "לי",
    "לו",
    "לה",
    "לנו",
    "לכם",
    "שזה",
    "שזהו",
}

FOLLOWUP_PREFIXES = (
    "ואם",
    "ואז",
    "אז",
    "אבל",
    "למה",
    "איך",
    "מה",
    "זה",
    "כלומר",
    "אפילו",
    "ובמקרה",
    "מה לגבי",
)

HEBREW_PREFIXES = ("ו", "ה", "ב", "כ", "ל", "מ", "ש")


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").lower()
    normalized = re.sub(r"[^\w\s\u0590-\u05ff]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def tokenize(text: str) -> set[str]:
    return {token for token in normalize_text(text).split() if len(token) > 1}


def stem_token(token: str) -> str:
    stemmed = token
    while len(stemmed) > 4 and stemmed[0] in HEBREW_PREFIXES:
        candidate = stemmed[1:]
        if len(candidate) < 3:
            break
        stemmed = candidate
    return stemmed


def stem_tokens(tokens: set[str]) -> set[str]:
    return {stem_token(token) for token in tokens}


def significant_tokens(tokens: set[str]) -> set[str]:
    return {token for token in tokens if token not in COMMON_TOKENS}


def is_followup_question(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    if normalized in {"?", "מה"}:
        return True
    if len(normalized) <= 18:
        return True
    return normalized.startswith(FOLLOWUP_PREFIXES)


def slugify_filename(text: str, fallback: str = "classified-question") -> str:
    base = unicodedata.normalize("NFKC", text or "")
    base = re.sub(r"[^\w\s\u0590-\u05ff-]", " ", base)
    base = re.sub(r"[\s_-]+", "-", base).strip("-").lower()
    return base[:80] or fallback
