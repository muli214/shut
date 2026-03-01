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

function escapeHtml(text) {
  return (text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderFlags(record) {
  const flags = [];
  flags.push(`<span class="flag">${record.topic}</span>`);
  if (record.thread_size > 1) {
    flags.push(`<span class="flag">שרשור ${record.thread_size}</span>`);
  }
  if (record.answer_delay_hours !== null && record.answer_delay_hours !== undefined) {
    flags.push(`<span class="flag ${record.timing_status === "suspicious" ? "danger" : "warning"}">מענה אחרי ${record.answer_delay_hours} שעות</span>`);
  }
  (record.suspicious_reasons || []).forEach(reason => {
    flags.push(`<span class="flag danger">${escapeHtml(reason)}</span>`);
  });
  return `<div class="flags">${flags.join("")}</div>`;
}

function renderThread(thread) {
  if (!thread || !thread.items || thread.items.length <= 1) {
    return "";
  }
  return `
    <div class="thread">
      <h3>שרשור המשך</h3>
      ${thread.items.map(item => `
        <div class="thread-item">
          <div class="meta">${escapeHtml(item.asker)} | ${escapeHtml(item.asked_at)}</div>
          <div class="question">${escapeHtml(item.question)}</div>
          <div class="answer">${escapeHtml(item.answer || "")}</div>
        </div>
      `).join("")}
    </div>
  `;
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

function renderMatch(data) {
  currentMatch = data;
  matchResult.innerHTML = `
    <article class="record-card ${data.suspicious_reasons && data.suspicious_reasons.length ? "review" : ""}">
      <div class="meta">ציון ${data.score} | ${escapeHtml(data.topic)} | ${escapeHtml(data.asked_at)} → ${escapeHtml(data.answered_at || "")}</div>
      <div class="question">${escapeHtml(data.question)}</div>
      <div class="answer">${escapeHtml(data.answer || "")}</div>
      ${renderFlags(data)}
      ${data.alternatives && data.alternatives.length ? `
        <div class="thread">
          <h3>חלופות נוספות (${data.total_options || (data.alternatives.length + 1)} אפשרויות)</h3>
          ${data.alternatives.map(item => `
            <div class="thread-item">
              <div class="question">${escapeHtml(item.question)}</div>
              <div class="answer">${escapeHtml(item.answer || "")}</div>
              <div class="meta">ציון ${item.score} | ${escapeHtml(item.topic)} | ${escapeHtml(item.asked_at || "")}</div>
            </div>
          `).join("")}
        </div>
      ` : ""}
      ${renderThread(data.thread)}
    </article>
  `;
  matchPanel.classList.remove("hidden");
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
  recordsList.innerHTML = loadedRecords.map(renderRecordCard).join("");
}

async function matchQuestion() {
  const text = questionInput.value.trim();
  if (!text) {
    statusMessage.textContent = "יש להזין שאלה.";
    return;
  }

  statusMessage.textContent = "מחפש התאמה...";
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
    statusMessage.textContent = "נמצאה התאמה.";
  } catch (error) {
    statusMessage.textContent = error.message;
    matchPanel.classList.add("hidden");
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
    statusMessage.textContent = "יש לכתוב מה לא מתאים.";
    return;
  }

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
  statusMessage.textContent = response.ok ? "הדיווח נשלח לאדמין." : (data.error || "שגיאה בשליחת הדיווח.");
});

matchButton.addEventListener("click", matchQuestion);
topicFilter.addEventListener("change", loadRecords);

loadTopics().then(loadRecords);
