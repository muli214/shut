const feedbackList = document.getElementById("feedbackList");
const reviewList = document.getElementById("reviewList");
const adminWarning = document.getElementById("adminWarning");

function escapeHtml(text) {
  return (text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function reviewCard(record) {
  return `
    <article class="record-card review">
      <div class="meta">${escapeHtml(record.asker)} | ${escapeHtml(record.asked_at)} | ${escapeHtml(record.topic)}</div>
      <div class="question">${escapeHtml(record.question)}</div>
      <div class="answer">${escapeHtml(record.answer || "")}</div>
      <div class="flags">
        ${(record.suspicious_reasons || []).map(reason => `<span class="flag danger">${escapeHtml(reason)}</span>`).join("")}
      </div>
      ${record.suggested_alternatives && record.suggested_alternatives.length ? `
        <div class="thread">
          <h3>הצעות חלופיות</h3>
          ${record.suggested_alternatives.map(item => `
            <div class="thread-item">
              <div class="question">${escapeHtml(item.question)}</div>
              <div class="answer">${escapeHtml(item.answer || "")}</div>
              <div class="meta">ציון ${item.score} | ${escapeHtml(item.topic)}</div>
            </div>
          `).join("")}
        </div>
      ` : ""}
      <div class="review-editor">
        <select id="status-${record.record_id}" class="select">
          <option value="pending">ממתין</option>
          <option value="approved">מאושר</option>
          <option value="fixed">תוקן</option>
          <option value="rejected">נדחה</option>
        </select>
        <textarea id="answer-${record.record_id}" class="textarea compact" placeholder="תשובה חלופית">${escapeHtml(record.answer || "")}</textarea>
        <textarea id="notes-${record.record_id}" class="textarea compact" placeholder="הערת אדמין"></textarea>
        <button class="button" data-record-id="${record.record_id}">שמור</button>
      </div>
    </article>
  `;
}

function feedbackCard(item) {
  return `
    <article class="record-card">
      <div class="meta">דיווח #${item.id} | ${escapeHtml(item.created_at)} | סטטוס ${escapeHtml(item.status)}</div>
      <div class="question">${escapeHtml(item.matched_question || "")}</div>
      <div class="answer">${escapeHtml(item.reason || "")}</div>
      <div class="actions">
        <button class="button button-secondary" data-feedback-id="${item.id}" data-feedback-status="reviewed">סמן כטופל</button>
        <button class="button button-secondary" data-feedback-id="${item.id}" data-feedback-status="dismissed">דחה</button>
      </div>
    </article>
  `;
}

async function loadDashboard() {
  const response = await fetch("/api/admin/dashboard");
  const data = await response.json();
  if (!response.ok) {
    adminWarning.textContent = data.error || "שגיאה בטעינת דשבורד.";
    adminWarning.classList.remove("hidden");
    return;
  }

  if (data.admin_default_password) {
    adminWarning.textContent = "סיסמת האדמין עדיין ברירת מחדל. עדכן SHUT_ADMIN_PASSWORD.";
    adminWarning.classList.remove("hidden");
  }

  feedbackList.innerHTML = data.feedback.map(feedbackCard).join("") || "<p class='muted'>אין דיווחים.</p>";
  reviewList.innerHTML = data.suspicious_records.map(reviewCard).join("") || "<p class='muted'>אין רשומות חשודות.</p>";
}

document.addEventListener("click", async (event) => {
  const reviewButton = event.target.closest("[data-record-id]");
  if (reviewButton) {
    const recordId = reviewButton.dataset.recordId;
    const status = document.getElementById(`status-${recordId}`).value;
    const overrideAnswer = document.getElementById(`answer-${recordId}`).value;
    const adminNotes = document.getElementById(`notes-${recordId}`).value;

    await fetch(`/api/admin/review/${recordId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status,
        override_answer: overrideAnswer,
        admin_notes: adminNotes
      })
    });
    loadDashboard();
    return;
  }

  const feedbackButton = event.target.closest("[data-feedback-id]");
  if (feedbackButton) {
    await fetch(`/api/admin/feedback/${feedbackButton.dataset.feedbackId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: feedbackButton.dataset.feedbackStatus })
    });
    loadDashboard();
  }
});

loadDashboard();
