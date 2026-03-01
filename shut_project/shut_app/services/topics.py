from .text_utils import normalize_text


TOPIC_RULES = {
    "שבת": ["שבת", "מוקצה", "הטמנה", "עירוב", "נר", "הבדלה", "קידוש"],
    "כשרות": ["כשר", "טרף", "בשר", "חלב", "פרווה", "כלי", "טבילה", "קומקום", "מצנם"],
    "ברכות ותפילה": ["ברכה", "לברך", "תפילה", "מניין", "מנחה", "שחרית", "זימון", "סידור", "מזוזה"],
    "מועדים": ["פסח", "סוכות", "שבועות", "פורים", "חנוכה", "יום העצמאות", "תשעת", "אב", "עומר"],
    "לימוד ושיעורים": ["שיעור", "זום", "ישיבה", "כולל", "הרב", "שיעורים", "פתיחה"],
    "צבא וחיים ציבוריים": ["צבא", "גיוס", "פלוגה", "חייל", "מחלקה", "טיפ", "גוי"],
    "זוגיות ומשפחה": ["חתונה", "שבע ברכות", "זוגיות", "הורים", "אשה", "אשתו"],
    "טהרה ורפואה": ["טהרה", "מקווה", "טבילה", "רפואה", "תרופה", "כאבי", "גרון"],
}


def classify_topic(*parts: str) -> tuple[str, str, float]:
    text = normalize_text(" ".join(part for part in parts if part))
    best_topic = "כללי"
    best_score = 0

    for topic, keywords in TOPIC_RULES.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score > best_score:
            best_topic = topic
            best_score = score

    confidence = min(1.0, 0.25 + (best_score * 0.18)) if best_score else 0.15
    return best_topic, best_topic, round(confidence, 2)
