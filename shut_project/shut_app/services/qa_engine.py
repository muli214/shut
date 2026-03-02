import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from .text_utils import (
    QUESTION_WORDS,
    is_followup_question,
    normalize_text,
    significant_tokens,
    slugify_filename,
    stem_tokens,
    tokenize,
)
from .topics import classify_topic


MAX_REASONABLE_ANSWER_HOURS = 48
THREAD_GAP_HOURS = 8
CONTEXT_WINDOW_HOURS = 48
SHORT_ANSWER_VALUES = {
    "כן",
    "לא",
    "מותר",
    "אסור",
    "אפשר",
    "אי אפשר",
    "חייב",
    "פטור",
}


@dataclass
class EngineResult:
    records: list[dict]
    records_by_id: dict[str, dict]
    threads: list[dict]
    topic_counts: dict[str, int]
    suspicious_records: list[dict]
    token_weights: dict[str, float]


def parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def make_record_id(question: str, asked_at: str) -> str:
    payload = f"{asked_at}|{question}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:16]


def build_token_weights(records: list[dict]) -> dict[str, float]:
    document_frequency: dict[str, int] = {}
    for record in records:
        for token in record["significant_stemmed_tokens"]:
            document_frequency[token] = document_frequency.get(token, 0) + 1

    total_documents = max(len(records), 1)
    return {
        token: math.log((total_documents + 1) / (frequency + 1)) + 1.0
        for token, frequency in document_frequency.items()
    }


def weighted_token_overlap(query_tokens: set[str], candidate_tokens: set[str], token_weights: dict[str, float]) -> float:
    if not query_tokens or not candidate_tokens:
        return 0.0

    intersection = query_tokens & candidate_tokens
    if not intersection:
        return 0.0

    matched_weight = sum(token_weights.get(token, 1.0) for token in intersection)
    query_weight = sum(token_weights.get(token, 1.0) for token in query_tokens)
    return matched_weight / query_weight if query_weight else 0.0


def question_score(candidate: dict, query: str, token_weights: dict[str, float]) -> float:
    normalized_query = normalize_text(query)
    normalized_candidate = candidate["normalized_question"]
    if not normalized_query or not normalized_candidate:
        return 0.0

    similarity = SequenceMatcher(None, normalized_query, normalized_candidate).ratio()
    query_tokens = tokenize(query)
    query_stems = stem_tokens(query_tokens)
    significant_query = significant_tokens(query_stems)

    overlap_ratio = 0.0
    if candidate["question_tokens"] and query_tokens:
        overlap_ratio = len(candidate["question_tokens"] & query_tokens) / len(candidate["question_tokens"] | query_tokens)

    stemmed_overlap = 0.0
    if candidate["stemmed_tokens"] and query_stems:
        stemmed_overlap = len(candidate["stemmed_tokens"] & query_stems) / len(candidate["stemmed_tokens"] | query_stems)

    significant_overlap = weighted_token_overlap(significant_query, candidate["significant_stemmed_tokens"], token_weights)

    topic_bonus = 0.0
    if candidate.get("topic") != "כללי":
        query_topic, _, confidence = classify_topic(query)
        if query_topic == candidate.get("topic"):
            topic_bonus = 0.05 * confidence

    containment_bonus = 0.08 if normalized_query in normalized_candidate or normalized_candidate in normalized_query else 0.0
    keyword_bonus = 0.05 if query_tokens & QUESTION_WORDS else 0.0

    score = (
        (similarity * 0.28)
        + (overlap_ratio * 0.1)
        + (stemmed_overlap * 0.1)
        + (significant_overlap * 0.42)
        + containment_bonus
        + keyword_bonus
        + topic_bonus
    )

    if len(significant_query) <= 1 and len(normalized_query) < 12:
        score *= 0.88
    if candidate.get("is_followup"):
        score *= 0.82
    if len(candidate.get("normalized_question", "")) < 10:
        score *= 0.86
    if len(candidate.get("significant_stemmed_tokens", set())) <= 1:
        score *= 0.9

    return min(score, 1.0)


def compute_answer_timing(question_at: datetime | None, answer_at: datetime | None) -> tuple[float | None, str, list[str]]:
    reasons: list[str] = []
    if question_at is None or answer_at is None:
        return None, "unknown", ["missing_timestamp"]

    delta_hours = round((answer_at - question_at).total_seconds() / 3600, 2)
    if delta_hours < 0:
        reasons.append("answer_before_question")
        return delta_hours, "invalid", reasons
    if delta_hours <= 24:
        return delta_hours, "ok", reasons
    if delta_hours <= MAX_REASONABLE_ANSWER_HOURS:
        reasons.append("slow_answer")
        return delta_hours, "warning", reasons

    reasons.append("late_answer")
    return delta_hours, "suspicious", reasons


def is_short_answer_text(answer: str) -> bool:
    normalized = normalize_text(answer)
    if not normalized:
        return True
    tokens = normalized.split()
    return normalized in SHORT_ANSWER_VALUES or len(tokens) <= 2 or len(normalized) <= 8


def should_continue_thread(previous: dict | None, current: dict) -> bool:
    if previous is None:
        return False
    prev_question_at = previous["question_at"]
    question_at = current["question_at"]
    if prev_question_at is None or question_at is None:
        return False

    hours_gap = (question_at - prev_question_at).total_seconds() / 3600
    if hours_gap < 0 or hours_gap > THREAD_GAP_HOURS:
        return False

    shared_topic = previous["topic"] == current["topic"] and current["topic"] != "כללי"
    same_asker = previous["asker"] == current["asker"]
    shared_tokens = len(previous["significant_stemmed_tokens"] & current["significant_stemmed_tokens"]) > 0
    followup = is_followup_question(current["question"])

    return shared_topic or (same_asker and shared_tokens) or (followup and (shared_tokens or same_asker))


def build_threads(records: list[dict]) -> list[dict]:
    threads: list[dict] = []
    current_thread: dict | None = None
    previous_record: dict | None = None

    for record in records:
        if current_thread is None or not should_continue_thread(previous_record, record):
            current_thread = {
                "id": f"thread-{len(threads) + 1}",
                "topic": record["topic"],
                "items": [],
            }
            threads.append(current_thread)

        record["thread_id"] = current_thread["id"]
        current_thread["items"].append(record)
        previous_record = record

    for thread in threads:
        item_count = len(thread["items"])
        followup_count = sum(1 for item in thread["items"] if item["is_followup"])
        thread["summary"] = {
            "item_count": item_count,
            "followup_count": followup_count,
            "topic": thread["topic"],
            "is_continuing_topic": item_count > 1,
        }
        for item in thread["items"]:
            item["thread_size"] = item_count
            item["thread_followups"] = followup_count

    return threads


def evaluate_record(record: dict) -> list[str]:
    reasons = list(record["timing_reasons"])
    if record["is_followup"] and record["thread_size"] == 1:
        reasons.append("followup_without_context")
    if len(record["normalized_question"]) < 6:
        reasons.append("very_short_question")
    if record["timing_status"] == "suspicious":
        reasons.append("timing_outlier")
    return sorted(set(reasons))


def load_engine(qa_data_file: Path) -> EngineResult:
    raw_records = json.loads(qa_data_file.read_text(encoding="utf-8"))
    records: list[dict] = []

    for item in raw_records:
        question = item.get("שאלה", "").strip()
        answer = item.get("תשובה", "").strip()
        asked_at = item.get("זמן שאלה", "")
        answered_at = item.get("זמן תשובה", "")
        question_tokens = tokenize(question)
        stemmed_question_tokens = stem_tokens(question_tokens)
        significant_stemmed = significant_tokens(stemmed_question_tokens)
        topic, topic_label, topic_confidence = classify_topic(question, answer)
        question_at = parse_timestamp(asked_at)
        answer_at = parse_timestamp(answered_at)
        answer_delay_hours, timing_status, timing_reasons = compute_answer_timing(question_at, answer_at)

        records.append(
            {
                "id": make_record_id(question, asked_at),
                "question": question,
                "answer": answer,
                "asker": item.get("שואל", ""),
                "asked_at": asked_at,
                "answered_at": answered_at,
                "question_at": question_at,
                "answer_at": answer_at,
                "normalized_question": normalize_text(question),
                "normalized_answer": normalize_text(answer),
                "is_short_answer": is_short_answer_text(answer),
                "question_tokens": question_tokens,
                "stemmed_tokens": stemmed_question_tokens,
                "significant_stemmed_tokens": significant_stemmed,
                "topic": topic,
                "topic_label": topic_label,
                "topic_confidence": topic_confidence,
                "is_followup": is_followup_question(question),
                "answer_delay_hours": answer_delay_hours,
                "timing_status": timing_status,
                "timing_reasons": timing_reasons,
            }
        )

    records.sort(key=lambda item: item["question_at"] or datetime.min)
    threads = build_threads(records)
    token_weights = build_token_weights(records)

    suspicious_records: list[dict] = []
    topic_counts: dict[str, int] = {}
    for record in records:
        record["suspicious_reasons"] = evaluate_record(record)
        record["needs_review"] = bool(record["suspicious_reasons"])
        topic_counts[record["topic"]] = topic_counts.get(record["topic"], 0) + 1
        if record["needs_review"]:
            suspicious_records.append(record)

    records_by_id = {record["id"]: record for record in records}
    return EngineResult(
        records=records,
        records_by_id=records_by_id,
        threads=threads,
        topic_counts=dict(sorted(topic_counts.items(), key=lambda item: (-item[1], item[0]))),
        suspicious_records=suspicious_records,
        token_weights=token_weights,
    )


class QAEngine:
    def __init__(self, qa_data_file: Path):
        self.qa_data_file = qa_data_file
        self.reload()

    def reload(self) -> None:
        engine_result = load_engine(self.qa_data_file)
        self.records = engine_result.records
        self.records_by_id = engine_result.records_by_id
        self.threads = engine_result.threads
        self.topic_counts = engine_result.topic_counts
        self.suspicious_records = engine_result.suspicious_records
        self.token_weights = engine_result.token_weights
        self.record_positions = {record["id"]: index for index, record in enumerate(self.records)}

    def match(self, query: str, limit: int = 3) -> list[dict]:
        query_significant = significant_tokens(stem_tokens(tokenize(query)))
        scored_records = []
        for record in self.records:
            score = question_score(record, query, self.token_weights)
            if score <= 0.15:
                continue
            scored_records.append((score, record))

        scored_records.sort(
            key=lambda item: (
                item[0],
                len(item[1]["significant_stemmed_tokens"] & query_significant),
                item[1]["topic_confidence"],
            ),
            reverse=True,
        )

        matches = []
        for score, record in scored_records[:limit]:
            matches.append(
                {
                    "record_id": record["id"],
                    "question": record["question"],
                    "answer": record["answer"],
                    "asker": record["asker"],
                    "asked_at": record["asked_at"],
                    "answered_at": record["answered_at"],
                    "score": round(score, 3),
                    "topic": record["topic"],
                    "topic_confidence": record["topic_confidence"],
                    "thread_id": record["thread_id"],
                    "thread_size": record["thread_size"],
                    "is_followup": record["is_followup"],
                    "is_short_answer": record["is_short_answer"],
                    "answer_delay_hours": record["answer_delay_hours"],
                    "timing_status": record["timing_status"],
                    "suspicious_reasons": record["suspicious_reasons"],
                    "suggested_filename": f"{slugify_filename(record['question'])}.txt",
                }
            )

        return matches

    def get_thread(self, thread_id: str, focus_record_id: str | None = None) -> dict | None:
        for thread in self.threads:
            if thread["id"] == thread_id:
                focused_index = 0
                if focus_record_id:
                    for index, item in enumerate(thread["items"]):
                        if item["id"] == focus_record_id:
                            focused_index = index
                            break
                return {
                    "id": thread["id"],
                    "topic": thread["topic"],
                    "summary": thread["summary"],
                    "focused_index": focused_index,
                    "items": [
                        {
                            "record_id": item["id"],
                            "question": item["question"],
                            "answer": item["answer"],
                            "asked_at": item["asked_at"],
                            "answered_at": item["answered_at"],
                            "asker": item["asker"],
                            "timing_status": item["timing_status"],
                            "answer_delay_hours": item["answer_delay_hours"],
                            "is_focus": item["id"] == focus_record_id,
                        }
                        for item in thread["items"]
                    ],
                }
        return None

    def answer_options(self, matches: list[dict], limit: int = 5) -> list[dict]:
        options: list[dict] = []
        seen_answers: set[str] = set()

        for match in matches:
            record = self.records_by_id.get(match["record_id"])
            normalized_answer = (record or {}).get("normalized_answer", "")
            answer_key = normalized_answer or f"record:{match['record_id']}"
            if answer_key in seen_answers:
                continue
            seen_answers.add(answer_key)
            options.append(match.copy())
            if len(options) >= limit:
                break

        return options

    def context_window(self, record_id: str, hours: int = CONTEXT_WINDOW_HOURS, max_items: int = 14) -> list[dict]:
        record = self.records_by_id.get(record_id)
        if record is None or record["question_at"] is None:
            return []

        record_time = record["question_at"]
        topic = record["topic"]
        items: list[dict] = []

        for candidate in self.records:
            candidate_time = candidate["question_at"]
            if candidate_time is None:
                continue
            delta_hours = abs((candidate_time - record_time).total_seconds() / 3600)
            if delta_hours > hours:
                continue

            same_topic = topic != "כללי" and candidate["topic"] == topic
            same_thread = candidate["thread_id"] == record["thread_id"]
            if not same_topic and not same_thread and candidate["id"] != record_id:
                continue

            items.append(
                {
                    "record_id": candidate["id"],
                    "question": candidate["question"],
                    "answer": candidate["answer"],
                    "asker": candidate["asker"],
                    "asked_at": candidate["asked_at"],
                    "answered_at": candidate["answered_at"],
                    "topic": candidate["topic"],
                    "hours_from_match": round((candidate_time - record_time).total_seconds() / 3600, 2),
                    "relative_position": "current" if candidate["id"] == record_id else ("before" if candidate_time < record_time else "after"),
                    "is_focus": candidate["id"] == record_id,
                }
            )

        items.sort(key=lambda item: abs(item["hours_from_match"]))
        if len(items) > max_items:
            items = sorted(items, key=lambda item: item["asked_at"])[:max_items]
        else:
            items = sorted(items, key=lambda item: item["asked_at"])
        return items

    def verify_match(self, query: str, matches: list[dict]) -> dict:
        if not matches:
            return {
                "level": "low",
                "label": "לא ודאי",
                "message": "לא נמצאה התאמה אמינה.",
                "reasons": ["no_matches"],
            }

        best_match = matches[0]
        best_record = self.records_by_id.get(best_match["record_id"])
        query_significant = significant_tokens(stem_tokens(tokenize(query)))
        next_score = matches[1]["score"] if len(matches) > 1 else 0.0
        score_gap = round(best_match["score"] - next_score, 3)
        context_items = self.context_window(best_match["record_id"])

        supporting_context = 0
        for item in context_items:
            if item["is_focus"]:
                continue
            context_record = self.records_by_id.get(item["record_id"])
            if context_record is None:
                continue
            overlap = len(context_record["significant_stemmed_tokens"] & query_significant)
            if overlap > 0 or context_record["thread_id"] == best_match["thread_id"]:
                supporting_context += 1

        reasons: list[str] = []
        short_answer = bool(best_record and best_record["is_short_answer"])
        if short_answer:
            reasons.append("short_answer_requires_context")
        if score_gap < 0.08:
            reasons.append("close_alternatives")
        if supporting_context == 0:
            reasons.append("no_supporting_context")
        if best_match["score"] < 0.5:
            reasons.append("weak_text_match")

        if short_answer and (best_match["score"] < 0.62 or score_gap < 0.12 or supporting_context == 0):
            return {
                "level": "low",
                "label": "לא ודאי",
                "message": "התשובה קצרה מדי כדי לסמוך עליה לבד. מוצגות חלופות והודעות סמוכות כדי לבדוק הקשר.",
                "reasons": reasons,
                "score_gap": score_gap,
                "supporting_context": supporting_context,
            }

        if best_match["score"] >= 0.72 and score_gap >= 0.12 and (supporting_context > 0 or not short_answer):
            return {
                "level": "high",
                "label": "ודאות גבוהה",
                "message": "נמצאה התאמה חזקה עם פער סביר מהחלופות.",
                "reasons": reasons,
                "score_gap": score_gap,
                "supporting_context": supporting_context,
            }

        return {
            "level": "medium",
            "label": "ודאות בינונית",
            "message": "יש התאמה טובה, אבל כדאי לבדוק גם חלופות והקשר סמוך.",
            "reasons": reasons,
            "score_gap": score_gap,
            "supporting_context": supporting_context,
        }

    def suggest_alternatives(self, record_id: str, limit: int = 3) -> list[dict]:
        record = self.records_by_id.get(record_id)
        if record is None:
            return []

        alternatives = []
        for score, candidate in ((question_score(candidate, record["question"], self.token_weights), candidate) for candidate in self.records):
            if candidate["id"] == record_id or score <= 0.2:
                continue
            alternatives.append(
                {
                    "record_id": candidate["id"],
                    "question": candidate["question"],
                    "answer": candidate["answer"],
                    "score": round(score, 3),
                    "topic": candidate["topic"],
                }
            )

        alternatives.sort(key=lambda item: item["score"], reverse=True)
        return alternatives[:limit]

    def list_records(self, topic: str | None = None, only_suspicious: bool = False) -> list[dict]:
        records = self.records
        if topic:
            records = [record for record in records if record["topic"] == topic]
        if only_suspicious:
            records = [record for record in records if record["needs_review"]]
        if not topic:
            records = sorted(records, key=lambda record: record["question_at"] or datetime.min, reverse=True)
            records = sorted(records, key=lambda record: record["topic"])

        return [
            {
                "record_id": record["id"],
                "question": record["question"],
                "answer": record["answer"],
                "asker": record["asker"],
                "asked_at": record["asked_at"],
                "answered_at": record["answered_at"],
                "topic": record["topic"],
                "topic_confidence": record["topic_confidence"],
                "thread_id": record["thread_id"],
                "thread_size": record["thread_size"],
                "answer_delay_hours": record["answer_delay_hours"],
                "timing_status": record["timing_status"],
                "suspicious_reasons": record["suspicious_reasons"],
            }
            for record in records
        ]
