from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request, send_from_directory

from ..db import get_db, utc_now
from ..services.text_utils import slugify_filename


public_bp = Blueprint("public", __name__)


def get_engine():
    return current_app.extensions["qa_engine"]


def get_review_map(record_ids: list[str]) -> dict[str, dict]:
    if not record_ids:
        return {}
    db = get_db()
    placeholders = ",".join("?" for _ in record_ids)
    rows = db.execute(
        f"SELECT record_id, status, override_question, override_answer, admin_notes, updated_at FROM qa_review WHERE record_id IN ({placeholders})",
        record_ids,
    ).fetchall()
    return {row["record_id"]: dict(row) for row in rows}


def apply_review(match: dict, review_map: dict[str, dict]) -> dict:
    review = review_map.get(match["record_id"])
    if review and review.get("override_answer"):
        match["answer"] = review["override_answer"]
        match["review_status"] = review["status"]
        match["admin_notes"] = review["admin_notes"]
        match["answer_source"] = "admin_override"
    else:
        match["review_status"] = review["status"] if review else "pending"
        match["admin_notes"] = review["admin_notes"] if review else ""
        match["answer_source"] = "dataset"
    return match


@public_bp.get("/")
def index():
    return render_template("index.html")


@public_bp.get("/admin/login")
def admin_login_page():
    return render_template("admin_login.html")


@public_bp.get("/data/<path:filename>")
def serve_data(filename: str):
    return send_from_directory(current_app.config["DATA_DIR"], filename)


@public_bp.get("/api/records")
def api_records():
    topic = request.args.get("topic") or None
    only_suspicious = request.args.get("only_suspicious") == "1"
    records = get_engine().list_records(topic=topic, only_suspicious=only_suspicious)
    review_map = get_review_map([record["record_id"] for record in records])

    for record in records:
        review = review_map.get(record["record_id"])
        if review and review.get("override_answer"):
            record["answer"] = review["override_answer"]
            record["review_status"] = review["status"]
            record["admin_notes"] = review["admin_notes"]
    return jsonify(records)


@public_bp.get("/api/topics")
def api_topics():
    engine = get_engine()
    return jsonify(
        {
            "topics": [{"name": topic, "count": count} for topic, count in engine.topic_counts.items()],
            "suspicious_count": len(engine.suspicious_records),
            "record_count": len(engine.records),
            "thread_count": len(engine.threads),
        }
    )


@public_bp.get("/api/thread/<thread_id>")
def api_thread(thread_id: str):
    thread = get_engine().get_thread(thread_id)
    if thread is None:
        return jsonify({"error": "שרשור לא נמצא."}), 404
    return jsonify(thread)


@public_bp.post("/api/match-question")
def api_match_question():
    payload = request.get_json(silent=True) or {}
    query_text = (payload.get("text") or "").strip()
    try:
        limit = max(1, min(int(payload.get("limit", 5)), 10))
    except (TypeError, ValueError):
        limit = 5
    if not query_text:
        return jsonify({"error": "יש להזין שאלה לבדיקה."}), 400

    matches = get_engine().match(query_text, limit=limit)
    if not matches:
        return jsonify({"error": "לא נמצאה התאמה."}), 404

    review_map = get_review_map([match["record_id"] for match in matches])
    matches = [apply_review(match, review_map) for match in matches]

    best_match = matches[0]
    best_match["alternatives"] = matches[1:]
    best_match["total_options"] = len(matches)
    best_match["thread"] = get_engine().get_thread(best_match["thread_id"])
    return jsonify(best_match)


@public_bp.post("/api/rename-file")
def api_rename_file():
    uploaded_file = request.files.get("file")
    query_text = (request.form.get("text") or "").strip()

    if uploaded_file is None or not uploaded_file.filename:
        return jsonify({"error": "יש להעלות קובץ."}), 400
    if not query_text:
        return jsonify({"error": "יש להזין את תוכן השאלה כדי לזהות את הקובץ."}), 400

    matches = get_engine().match(query_text, limit=1)
    if not matches:
        return jsonify({"error": "לא נמצאה התאמה עבור שינוי שם הקובץ."}), 404

    match = apply_review(matches[0], get_review_map([matches[0]["record_id"]]))
    original_suffix = Path(uploaded_file.filename).suffix or ".txt"
    original_stem = Path(uploaded_file.filename).stem
    new_stem = slugify_filename(match["question"], fallback=slugify_filename(original_stem))
    new_filename = f"{new_stem}{original_suffix}"
    target_path = current_app.config["UPLOADS_DIR"] / new_filename

    counter = 1
    while target_path.exists():
        new_filename = f"{new_stem}-{counter}{original_suffix}"
        target_path = current_app.config["UPLOADS_DIR"] / new_filename
        counter += 1

    uploaded_file.save(target_path)
    return jsonify(
        {
            "original_filename": uploaded_file.filename,
            "renamed_filename": new_filename,
            "saved_path": str(target_path.relative_to(current_app.config["DATA_DIR"].parent)),
            "match": match,
        }
    )


@public_bp.post("/api/feedback")
def api_feedback():
    payload = request.get_json(silent=True) or {}
    record_id = (payload.get("record_id") or "").strip()
    reason = (payload.get("reason") or "").strip()
    query_text = (payload.get("query_text") or "").strip()
    matched_question = (payload.get("matched_question") or "").strip()
    matched_answer = (payload.get("matched_answer") or "").strip()

    if not record_id or not reason:
        return jsonify({"error": "יש לשלוח מזהה רשומה וסיבת דיווח."}), 400

    db = get_db()
    db.execute(
        """
        INSERT INTO feedback (record_id, query_text, matched_question, matched_answer, reason, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'open', ?)
        """,
        (record_id, query_text, matched_question, matched_answer, reason, utc_now()),
    )
    db.commit()
    return jsonify({"status": "ok"})
