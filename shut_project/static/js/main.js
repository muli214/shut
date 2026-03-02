const questionInput = document.getElementById("questionInput");
const matchButton = document.getElementById("matchButton");
const statusMessage = document.getElementById("statusMessage");
const matchPanel = document.getElementById("matchPanel");
const matchResult = document.getElementById("matchResult");
const reportButton = document.getElementById("reportButton");
const feedbackReason = document.getElementById("feedbackReason");
const feedbackActions = document.getElementById("feedbackActions");
const sendFeedbackButton = document.getElementById("sendFeedbackButton");
const recordsList = document.getElementById("recordsList");
const topicFilter = document.getElementById("topicFilter");
const topicSummary = document.getElementById("topicSummary");
const optionsLimit = document.getElementById("optionsLimit");

let currentMatch = null;
let loadedRecords = [];

function setStatus(message, state = "") {
  statusMessage.textContent = message;
  statusMessage.className = "status live-status";
  if (state) {
    statusMessage.classList.add(`is-${state}`);
  }
}

function animatePanel(panel) {
  panel.classList.remove("hidden");
  panel.animate(
    [
      { opacity: 0, transform: "translateY(18px)" },
      { opacity: 1, transform: "translateY(0)" }
    ],
    { duration: 360, easing: "cubic-bezier(.2,.8,.2,1)" }
  );
}

function escapeHtml(text) {
  return (text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderFlags(record) {
  const flags = [];
  flags.push(`<span class="flag">${escapeHtml(record.topic || "כללי")}</span>`);
  if (record.thread_size > 1) {
    flags.push(`<span class="flag">רצף של ${record.thread_size} שאלות</span>`);
  }
  if (record.is_followup) {
    flags.push(`<span class="flag">שאלת המשך</span>`);
  }
  if (record.answer_delay_hours !== null && record.answer_delay_hours !== undefined) {
    const timingClass = record.timing_status === "suspicious" ? "danger" : "warning";
    flags.push(`<span class="flag ${timingClass}">מענה אחרי ${record.answer_delay_hours} שעות</span>`);
  }
  (record.suspicious_reasons || []).forEach(reason => {
    flags.push(`<span class="flag danger">${escapeHtml(reason)}</span>`);
  });
  return flags.length ? `<div class="flags">${flags.join("")}</div>` : "";
}

function renderRecordCard(record) {
  return `
    <article class="record-card ${record.suspicious_reasons && record.suspicious_reasons.length ? "review" : ""}">
      <div class="meta">${escapeHtml(record.asker)} | ${escapeHtml(record.asked_at)} | ${escapeHtml(record.topic)}</div>
      <div class="question">${escapeHtml(record.question)}</div>
      <div class="answer">${escapeHtml(record.answer || "")}</div>
      ${renderFlags(record)}
    </article>
  `;
}

function renderAlternative(option, index) {
  return `
    <article class="option-card">
      <div class="option-rank">אפשרות ${index + 2}</div>
      <div class="question">${escapeHtml(option.question)}</div>
      <div class="answer">${escapeHtml(option.answer || "")}</div>
      <div class="meta">ציון ${option.score} | ${escapeHtml(option.topic)} | ${escapeHtml(option.asked_at || "")}</div>
    </article>
  `;
}

function renderVerification(verification) {
  if (!verification) {
    return "";
  }

  return `
    <section class="verification-panel verification-${escapeHtml(verification.level || "medium")}">
      <div class="journey-header">
        <div>
          <span class="eyebrow">Match Confidence</span>
          <h3>${escapeHtml(verification.label || "בדיקת ודאות")}</h3>
        </div>
        <div class="journey-summary">${escapeHtml(verification.message || "")}</div>
      </div>
      ${(verification.reasons || []).length ? `
        <div class="flags">
          ${verification.reasons.map(reason => `<span class="flag">${escapeHtml(reason)}</span>`).join("")}
        </div>
      ` : ""}
    </section>
  `;
}

function renderContextWindow(items) {
  if (!items || !items.length) {
    return "";
  }

  return `
    <section class="context-panel">
      <div class="journey-header">
        <div>
          <span class="eyebrow">Nearby Chat</span>
          <h3>הודעות לפני ואחרי בטווח של יומיים</h3>
        </div>
        <div class="journey-summary">כדי לבדוק הקשר ולא לסמוך על כן או לא לבד</div>
      </div>
      <div class="context-list">
        ${items.map(item => `
          <article class="context-card ${item.is_focus ? "is-focus" : ""}">
            <div class="context-rail ${item.relative_position}">${item.is_focus ? "התאמה" : item.relative_position === "before" ? "לפני" : "אחרי"}</div>
            <div class="context-body">
              <div class="meta">${escapeHtml(item.asker)} | ${escapeHtml(item.asked_at)} | ${escapeHtml(item.topic)}</div>
              <div class="question">${escapeHtml(item.question)}</div>
              <div class="answer">${escapeHtml(item.answer || "")}</div>
            </div>
          </article>
        `).join("")}
      </div>
    </section>
  `;
}

function renderThread(thread) {
  if (!thread || !thread.items || !thread.items.length) {
    return "";
  }

  return `
    <section class="journey-panel">
      <div class="journey-header">
        <div>
          <span class="eyebrow">Conversation Flow</span>
          <h3>השאלות בהמשכים</h3>
        </div>
        <div class="journey-summary">שרשור בנושא ${escapeHtml(thread.topic || "כללי")} | ${thread.items.length} תחנות</div>
      </div>
      <div class="journey-steps">
        ${thread.items.map((item, index) => `
          <article class="journey-step ${item.is_focus ? "is-current" : ""}">
            <div class="journey-index">${index + 1}</div>
            <div class="journey-body">
              <div class="meta">${escapeHtml(item.asker)} | ${escapeHtml(item.asked_at)}</div>
              <div class="question">${escapeHtml(item.question)}</div>
              <div class="answer">${escapeHtml(item.answer || "")}</div>
            </div>
          </article>
        `).join("")}
      </div>
    </section>
  `;
}

function renderMatch(data) {
  currentMatch = data;
  matchResult.innerHTML = `
    <section class="result-stack">
      <article class="record-card match-hero ${data.suspicious_reasons && data.suspicious_reasons.length ? "review" : ""}">
        <div class="result-topline">
          <span class="result-badge">${data.verification && data.verification.level === "low" ? "התאמה לא ודאית" : "התשובה המובילה"}</span>
          <span class="result-score">ציון ${data.score}</span>
        </div>
        <div class="meta">${escapeHtml(data.topic)} | ${escapeHtml(data.asked_at)}${data.answered_at ? ` | נענה ב־${escapeHtml(data.answered_at)}` : ""}</div>
        <div class="question">${escapeHtml(data.question)}</div>
        <div class="answer">${escapeHtml(data.answer || "")}</div>
        ${renderFlags(data)}
      </article>
      ${renderVerification(data.verification)}
      ${data.alternatives && data.alternatives.length ? `
        <section class="options-panel">
          <div class="journey-header">
            <div>
              <span class="eyebrow">Possible Answers</span>
              <h3>עוד תשובות אפשריות</h3>
            </div>
            <div class="journey-summary">${data.total_options} אפשרויות שונות מתוך ${data.raw_match_count} התאמות</div>
          </div>
          <div class="options-grid">
            ${data.alternatives.map(renderAlternative).join("")}
          </div>
        </section>
      ` : ""}
      ${renderContextWindow(data.context_window)}
      ${renderThread(data.thread)}
    </section>
  `;
  animatePanel(matchPanel);
  matchPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadTopics() {
  const response = await fetch("/api/topics");
  const data = await response.json();
  topicSummary.innerHTML = data.topics.map(topic => `<span class="chip">${escapeHtml(topic.name)} (${topic.count})</span>`).join("");
  topicFilter.innerHTML = `<option value="">כל הנושאים</option>` + data.topics.map(topic => `<option value="${escapeHtml(topic.name)}">${escapeHtml(topic.name)} (${topic.count})</option>`).join("");
}

async function loadRecords() {
  const topic = topicFilter.value;
  const url = topic ? `/api/records?topic=${encodeURIComponent(topic)}` : "/api/records";
  const response = await fetch(url);
  loadedRecords = await response.json();
  recordsList.innerHTML = loadedRecords.map(renderRecordCard).join("") || "<p class='muted'>לא נמצאו רשומות.</p>";
}

async function matchQuestion() {
  const text = questionInput.value.trim();
  if (!text) {
    setStatus("יש להזין שאלה.", "error");
    return;
  }

  matchButton.disabled = true;
  setStatus("מחפש שאלה דומה ותשובות אפשריות...", "loading");
  try {
    const response = await fetch("/api/match-question", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, limit: Number(optionsLimit.value || 5) })
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "שגיאה בזיהוי.");
    }
    renderMatch(data);
    const statusState = data.verification && data.verification.level === "low" ? "error" : "success";
    const statusMessageText = data.verification && data.verification.level === "low"
      ? "ההתאמה לא ודאית. בדוק חלופות והקשר סמוך."
      : `נמצאו ${data.total_options || 1} כיווני מענה.`;
    setStatus(statusMessageText, statusState);
  } catch (error) {
    setStatus(error.message, "error");
    matchPanel.classList.add("hidden");
  } finally {
    matchButton.disabled = false;
  }
}

reportButton.addEventListener("click", () => {
  feedbackReason.classList.remove("hidden");
  feedbackActions.classList.remove("hidden");
});

sendFeedbackButton.addEventListener("click", async () => {
  if (!currentMatch) {
    return;
  }
  const reason = feedbackReason.value.trim();
  if (!reason) {
    setStatus("יש לכתוב מה לא מתאים.", "error");
    return;
  }

  sendFeedbackButton.disabled = true;
  const response = await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      record_id: currentMatch.record_id,
      query_text: questionInput.value.trim(),
      matched_question: currentMatch.question,
      matched_answer: currentMatch.answer,
      reason
    })
  });
  const data = await response.json();
  setStatus(response.ok ? "הדיווח נשלח לאדמין." : (data.error || "שגיאה בשליחת הדיווח."), response.ok ? "success" : "error");
  sendFeedbackButton.disabled = false;
});

matchButton.addEventListener("click", matchQuestion);
topicFilter.addEventListener("change", loadRecords);
questionInput.addEventListener("keydown", event => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    matchQuestion();
  }
});

loadTopics().then(loadRecords);
