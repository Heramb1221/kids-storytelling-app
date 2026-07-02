const session = Auth.requireRole("student");

if (session) {
  document.getElementById("studentName").textContent = `🌙 ${session.name}`;
}

const emojiCycle = ["📗", "📘", "📙", "📕", "📓"];

async function loadStories() {
  const grid = document.getElementById("storyGrid");
  const empty = document.getElementById("emptyState");
  try {
    const { stories } = await apiCall("/stories");
    grid.innerHTML = "";
    empty.style.display = stories.length ? "none" : "block";

    stories.forEach((story, i) => {
      const card = document.createElement("div");
      card.className = "story-card";
      card.innerHTML = `
        <span class="emoji">${emojiCycle[i % emojiCycle.length]}</span>
        <h3>${escapeHtml(story.title)}</h3>
        <div class="meta">by ${escapeHtml(story.teacher_username)}</div>
      `;
      card.addEventListener("click", () => openStory(story.story_id));
      grid.appendChild(card);
    });
  } catch (err) {
    showToast(err.message, "error");
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---------- Story modal ----------
const overlay = document.getElementById("modalOverlay");
const modalTitle = document.getElementById("modalTitle");
const modalAuthor = document.getElementById("modalAuthor");
const modalText = document.getElementById("modalText");
const modalAudio = document.getElementById("modalAudio");
const playButton = document.getElementById("playButton");

async function openStory(storyId) {
  overlay.classList.add("open");
  modalTitle.textContent = "Loading...";
  modalAuthor.textContent = "";
  modalText.textContent = "";
  modalAudio.removeAttribute("src");
  modalAudio.load();
  setPlayIcon("▶");

  try {
    const story = await apiCall(`/stories/${storyId}`);
    modalTitle.textContent = story.title;
    modalAuthor.textContent = `written by ${story.teacher_username}`;
    modalText.textContent = story.text || "This story isn't ready yet.";

    console.log("Story API response:", story);

    if (story.audio_url) {
      modalAudio.src = story.audio_url;
      modalAudio.load();
      // Try to autoplay - browsers may block this until the user clicks
      // the big play button, which is fine, that's what it's there for.
      modalAudio.play().catch((err) => {
        console.warn("Autoplay was blocked, waiting for a manual play click:", err);
      });
    } else {
      console.warn("No audio_url in the API response - story status was:", story.status);
      showToast("This story doesn't have audio yet. Ask your teacher to check on it!", "error");
    }
  } catch (err) {
    console.error("Failed to load story:", err);
    modalText.textContent = "Oops! We couldn't load this story. Please try again.";
  }
}

modalAudio.addEventListener("error", () => {
  const err = modalAudio.error;
  const messages = {
    1: "Loading the audio was stopped.",
    2: "A network error prevented the audio from loading.",
    3: "The audio file could not be decoded.",
    4: "The audio file could not be found (its link may have expired).",
  };
  const msg = err ? (messages[err.code] || "Unknown audio error") : "Unknown audio error";
  console.error("Audio playback error:", msg, err);
  showToast(`Audio problem: ${msg}`, "error");
});

modalAudio.addEventListener("play", () => setPlayIcon("⏸"));
modalAudio.addEventListener("pause", () => setPlayIcon("▶"));

function setPlayIcon(icon) {
  playButton.textContent = icon;
}

function closeModal() {
  overlay.classList.remove("open");
  modalAudio.pause();
  modalAudio.currentTime = 0;
}

document.getElementById("closeModal").addEventListener("click", closeModal);
overlay.addEventListener("click", (e) => {
  if (e.target === overlay) closeModal();
});
playButton.addEventListener("click", () => {
  if (!modalAudio.src) {
    showToast("There's no audio loaded for this story yet.", "error");
    return;
  }
  if (modalAudio.paused) {
    modalAudio.play().catch((err) => {
      console.error("Play failed:", err);
      showToast("Couldn't play the audio. Check the browser console for details.", "error");
    });
  } else {
    modalAudio.pause();
  }
});

loadStories();
setInterval(loadStories, 20000);
