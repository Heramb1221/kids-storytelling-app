const session = Auth.requireRole("teacher");

if (session) {
  document.getElementById("teacherName").textContent = `🍎 ${session.name}`;
}

// ---------- Tab switching ----------
const tabPaste = document.getElementById("tabPaste");
const tabFile = document.getElementById("tabFile");
const modePaste = document.getElementById("modePaste");
const modeFile = document.getElementById("modeFile");

tabPaste.addEventListener("click", () => {
  tabPaste.classList.add("active");
  tabFile.classList.remove("active");
  modePaste.classList.add("active");
  modeFile.classList.remove("active");
});

tabFile.addEventListener("click", () => {
  tabFile.classList.add("active");
  tabPaste.classList.remove("active");
  modeFile.classList.add("active");
  modePaste.classList.remove("active");
});

// ---------- Paste-text upload ----------
document.getElementById("pasteSubmit").addEventListener("click", async () => {
  const title = document.getElementById("pasteTitle").value.trim();
  const text = document.getElementById("pasteText").value.trim();
  const errorBox = document.getElementById("pasteError");
  const btn = document.getElementById("pasteSubmit");
  errorBox.textContent = "";

  if (!title || !text) {
    errorBox.textContent = "Please add a title and some story text.";
    return;
  }

  btn.disabled = true;
  btn.textContent = "Publishing...";

  try {
    await apiCall("/stories/paste", { method: "POST", auth: true, body: { title, text } });
    document.getElementById("pasteTitle").value = "";
    document.getElementById("pasteText").value = "";
    showToast(`"${title}" is being turned into a read-aloud! 🎧`);
    loadStories();
  } catch (err) {
    errorBox.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Publish Story 🚀";
  }
});

// ---------- File upload ----------
const fileInput = document.getElementById("fileInput");
const fileDrop = document.getElementById("fileDrop");
const fileDropLabel = document.getElementById("fileDropLabel");

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) {
    fileDrop.classList.add("has-file");
    fileDropLabel.textContent = `✅ ${fileInput.files[0].name}`;
  }
});

document.getElementById("fileSubmit").addEventListener("click", async () => {
  const title = document.getElementById("fileTitle").value.trim();
  const file = fileInput.files[0];
  const errorBox = document.getElementById("fileError");
  const btn = document.getElementById("fileSubmit");
  errorBox.textContent = "";

  if (!title || !file) {
    errorBox.textContent = "Please add a title and choose a .txt file.";
    return;
  }

  btn.disabled = true;
  btn.textContent = "Uploading...";

  try {
    const { upload_url } = await apiCall("/stories/upload-url", {
      method: "POST",
      auth: true,
      body: { title },
    });

    const putRes = await fetch(upload_url, {
      method: "PUT",
      headers: { "Content-Type": "text/plain" },
      body: file,
    });

    if (!putRes.ok) throw new Error("Upload to storage failed. Please try again.");

    document.getElementById("fileTitle").value = "";
    fileInput.value = "";
    fileDrop.classList.remove("has-file");
    fileDropLabel.textContent = "Click to choose a .txt file";
    showToast(`"${title}" is being turned into a read-aloud! 🎧`);
    loadStories();
  } catch (err) {
    errorBox.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Upload Story 🚀";
  }
});

// ---------- Story list ----------
async function loadStories() {
  const grid = document.getElementById("storyGrid");
  const empty = document.getElementById("emptyState");
  try {
    const { stories } = await apiCall(`/stories?teacher=${encodeURIComponent(session.username)}`, { auth: true });
    grid.innerHTML = "";
    empty.style.display = stories.length ? "none" : "block";

    stories.forEach((story) => {
      const card = document.createElement("div");
      card.className = "story-card";
      const badge = badgeFor(story.status);
      card.innerHTML = `
        <span class="emoji">${emojiFor(story.status)}</span>
        <h3>${escapeHtml(story.title)}</h3>
        <div class="meta">${new Date(story.created_at).toLocaleDateString()}</div>
        <span class="badge ${badge.className}">${badge.label}</span>
      `;
      grid.appendChild(card);
    });
  } catch (err) {
    showToast(err.message, "error");
  }
}

function badgeFor(status) {
  if (status === "ready") return { className: "badge-ready", label: "✅ Ready" };
  if (status === "error") return { className: "badge-error", label: "⚠️ Error" };
  return { className: "badge-processing", label: "⏳ Processing" };
}

function emojiFor(status) {
  if (status === "ready") return "📗";
  if (status === "error") return "📕";
  return "📙";
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---------- Notifications (SNS -> SQS polling) ----------
async function checkNotifications() {
  try {
    const { notifications } = await apiCall("/notifications", { auth: true });
    if (notifications.length) {
      notifications.forEach((n) => showToast(`🎉 "${n.title}" is ready to read!`));
      loadStories();
    }
  } catch (err) {
    // silent - notifications are best-effort
  }
}

loadStories();
setInterval(loadStories, 15000);
setInterval(checkNotifications, 6000);
