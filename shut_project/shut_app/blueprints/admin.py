from functools import wraps

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from ..db import get_db, utc_now


admin_bp = Blueprint("admin", __name__)


def is_admin_logged_in() -> bool:
    return bool(session.get("admin_authenticated"))


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin_logged_in():
            if request.path.startswith("/api/"):
                return jsonify({"error": "נדרשת התחברות אדמין."}), 401
            return redirect(url_for("public.admin_login_page"))
        return view(*args, **kwargs)

    return wrapped


@admin_bp.post("/admin/login")
def admin_login():
    payload = request.get_json(silent=True) if request.is_json else {}
    username = ((request.form.get("username") if not request.is_json else payload.get("username")) or "").strip()
    password = ((request.form.get("password") if not request.is_json else payload.get("password")) or "").strip()

    if (
        username == current_app.config["ADMIN_USERNAME"]
        and password == current_app.config["ADMIN_PASSWORD"]
    ):
        session["admin_authenticated"] = True
        if request.is_json:
            return jsonify({"status": "ok"})
        return redirect(url_for("admin.admin_dashboard"))

    if request.is_json:
        return jsonify({"error": "שם משתמש או סיסמה שגויים."}), 401
    return render_template("admin_login.html", error="שם משתמש או סיסמה שגויים."), 401


@admin_bp.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("public.index"))


@admin_bp.get("/admin")
@require_admin
def admin_dashboard():
    return render_template("admin.html")


@admin_bp.get("/api/admin/dashboard")
@require_admin
def api_admin_dashboard():
    engine = current_app.extensions["qa_engine"]
    try:
        limit = max(1, min(int(request.args.get("limit", 40)), 200))
    except ValueError:
        limit = 40
    include_alternatives = request.args.get("include_alternatives") == "1"
    db = get_db()
    reviews = {
        row["record_id"]: dict(row)
        for row in db.execute("SELECT * FROM qa_review ORDER BY updated_at DESC").fetchall()
    }
    feedback = [dict(row) for row in db.execute("SELECT * FROM feedback ORDER BY created_at DESC").fetchall()]

    suspicious = []
    for record in engine.list_records(only_suspicious=True)[:limit]:
        review = reviews.get(record["record_id"])
        if review and review.get("override_answer"):
            record["answer"] = review["override_answer"]
            record["review_status"] = review["status"]
            record["admin_notes"] = review["admin_notes"]
        if include_alternatives:
            record["suggested_alternatives"] = engine.suggest_alternatives(record["record_id"])
        suspicious.append(record)

    return jsonify(
        {
            "suspicious_records": suspicious,
            "feedback": feedback,
            "topics": [{"name": topic, "count": count} for topic, count in engine.topic_counts.items()],
            "admin_default_password": current_app.config["ADMIN_PASSWORD"] == "change-me",
        }
    )


@admin_bp.post("/api/admin/review/<record_id>")
@require_admin
def api_admin_review(record_id: str):
    payload = request.get_json(silent=True) or {}
    status = (payload.get("status") or "pending").strip()
    override_question = (payload.get("override_question") or "").strip()
    override_answer = (payload.get("override_answer") or "").strip()
    admin_notes = (payload.get("admin_notes") or "").strip()

    db = get_db()
    db.execute(
        """
        INSERT INTO qa_review (record_id, status, override_question, override_answer, admin_notes, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(record_id) DO UPDATE SET
            status=excluded.status,
            override_question=excluded.override_question,
            override_answer=excluded.override_answer,
            admin_notes=excluded.admin_notes,
            updated_at=excluded.updated_at
        """,
        (record_id, status, override_question, override_answer, admin_notes, utc_now()),
    )
    db.commit()
    return jsonify({"status": "ok"})


@admin_bp.post("/api/admin/feedback/<int:feedback_id>")
@require_admin
def api_admin_feedback(feedback_id: int):
    payload = request.get_json(silent=True) or {}
    status = (payload.get("status") or "reviewed").strip()
    db = get_db()
    db.execute(
        "UPDATE feedback SET status = ?, reviewed_at = ? WHERE id = ?",
        (status, utc_now(), feedback_id),
    )
    db.commit()
    return jsonify({"status": "ok"})
