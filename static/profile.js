const state = { user: null };

const accountSummary = document.querySelector("#accountSummary");
const authForm = document.querySelector("#authForm");
const authUsername = document.querySelector("#authUsername");
const authPassword = document.querySelector("#authPassword");
const logoutButton = document.querySelector("#logoutButton");
const sourceNote = document.querySelector("#sourceNote");
const profileComments = document.querySelector("#profileComments");
const profileTeams = document.querySelector("#profileTeams");
const followList = document.querySelector("#followList");

function formatTime(value) {
  if (!value) return "TBD";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function updateAuthUi() {
  if (state.user) {
    accountSummary.textContent = `Signed in as ${state.user.username}`;
    authForm.hidden = true;
    logoutButton.hidden = false;
  } else {
    accountSummary.textContent = "Signed out";
    authForm.hidden = false;
    logoutButton.hidden = true;
  }
}

function renderFollows(follows) {
  followList.innerHTML = "";
  if (!follows.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No followed teams yet.";
    followList.append(empty);
    return;
  }
  for (const follow of follows) {
    const item = document.createElement("article");
    item.className = "follow-item";
    const copy = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = follow.team_name;
    const meta = document.createElement("span");
    meta.textContent = `${follow.game} / followed ${formatTime(follow.created_at)}`;
    copy.append(name, meta);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Unfollow";
    remove.addEventListener("click", async () => {
      const response = await fetch(`/api/follows/${encodeURIComponent(follow.team_id)}`, { method: "DELETE" });
      if (response.ok) await loadProfile();
    });
    item.append(copy, remove);
    followList.append(item);
  }
}

async function loadCurrentUser() {
  const response = await fetch("/api/auth/me");
  const payload = await response.json();
  state.user = payload.user;
  updateAuthUi();
  await loadProfile();
}

async function loadProfile() {
  if (!state.user) {
    sourceNote.textContent = "Login to view profile.";
    profileComments.textContent = "0";
    profileTeams.textContent = "0";
    renderFollows([]);
    return;
  }
  const response = await fetch("/api/profile");
  const payload = await response.json();
  if (!response.ok) {
    sourceNote.textContent = payload.error || "Profile unavailable";
    return;
  }
  sourceNote.textContent = `Member since ${formatTime(payload.user.created_at)}.`;
  profileComments.textContent = String(payload.stats.comments);
  profileTeams.textContent = String(payload.stats.followed_teams);
  renderFollows(payload.followed_teams);
}

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const mode = event.submitter?.dataset.mode || "login";
  const response = await fetch(`/api/auth/${mode}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: authUsername.value.trim(), password: authPassword.value }),
  });
  const payload = await response.json();
  if (!response.ok) {
    sourceNote.textContent = payload.error || "Account error";
    return;
  }
  state.user = payload.user;
  authPassword.value = "";
  updateAuthUi();
  await loadProfile();
});

logoutButton.addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  state.user = null;
  updateAuthUi();
  await loadProfile();
});

loadCurrentUser();
