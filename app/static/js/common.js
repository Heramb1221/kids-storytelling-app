// Shared helpers used across all pages.

const Auth = {
  KEY: "storytime_session",

  save(session) {
    localStorage.setItem(this.KEY, JSON.stringify(session));
  },

  get() {
    const raw = localStorage.getItem(this.KEY);
    return raw ? JSON.parse(raw) : null;
  },

  clear() {
    localStorage.removeItem(this.KEY);
  },

  requireRole(role) {
    const session = this.get();
    if (!session || session.role !== role) {
      window.location.href = "/";
      return null;
    }
    return session;
  },
};

function showToast(message, kind) {
  const stack = document.getElementById("toastStack");
  if (!stack) return;
  const el = document.createElement("div");
  el.className = "toast";
  if (kind === "error") {
    el.style.background = "#ff5c7a";
    el.style.color = "white";
  }
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => el.remove(), 5000);
}

async function apiCall(path, { method = "GET", body, auth = false } = {}) {
  if (!window.API_ENDPOINT) {
    throw new Error("App is not configured yet. Run the AWS setup script first.");
  }
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const session = Auth.get();
    if (!session) throw new Error("Not logged in");
    headers["Authorization"] = `Bearer ${session.token}`;
  }
  const res = await fetch(window.API_ENDPOINT + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

function logout() {
  Auth.clear();
  window.location.href = "/";
}
