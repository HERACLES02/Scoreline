const state = {
  status: "live",
  game: "all",
  timer: null,
  selectedMatch: null,
  user: null,
};

const tabs = document.querySelectorAll(".tab");
const gameSelect = document.querySelector("#gameSelect");
const matchList = document.querySelector("#matchList");
const template = document.querySelector("#matchTemplate");
const sectionTitle = document.querySelector("#sectionTitle");
const providerStatus = document.querySelector("#providerStatus");
const sourceNote = document.querySelector("#sourceNote");
const matchCount = document.querySelector("#matchCount");
const refreshButton = document.querySelector("#refreshButton");
const discussionTitle = document.querySelector("#discussionTitle");
const discussionCount = document.querySelector("#discussionCount");
const commentList = document.querySelector("#commentList");
const commentForm = document.querySelector("#commentForm");
const commentBody = document.querySelector("#commentBody");
const authForm = document.querySelector("#authForm");
const authUsername = document.querySelector("#authUsername");
const authPassword = document.querySelector("#authPassword");
const accountSummary = document.querySelector("#accountSummary");
const logoutButton = document.querySelector("#logoutButton");

const statusLabels = {
  live: "Live matches",
  upcoming: "Upcoming matches",
  results: "Recent results",
};

commentBody.disabled = true;
commentForm.querySelector("button").disabled = true;

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
  updateCommentComposer();
}

function updateCommentComposer() {
  const enabled = Boolean(state.user && state.selectedMatch);
  commentBody.disabled = !enabled;
  commentForm.querySelector("button").disabled = !enabled;
  commentBody.placeholder = state.user ? "Add a match comment" : "Login to comment";
}

function formatTime(value) {
  if (!value) return "TBD";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "TBD";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function initials(name) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function renderMatches(matches) {
  matchList.innerHTML = "";
  matchCount.textContent = String(matches.length);

  if (!matches.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No matches found for this filter.";
    matchList.append(empty);
    return;
  }

  for (const match of matches) {
    const card = template.content.firstElementChild.cloneNode(true);
    card.dataset.matchId = match.id;
    card.querySelector(".game").textContent = match.game;
    card.querySelector(".league").textContent = `${match.league} / ${match.tournament}`;
    card.querySelector(".time").textContent = formatTime(match.starts_at);
    card.querySelector(".team-one .team-name").textContent = match.team_one.name;
    card.querySelector(".team-two .team-name").textContent = match.team_two.name;
    card.querySelector(".team-one .team-mark").textContent = initials(match.team_one.name);
    card.querySelector(".team-two .team-mark").textContent = initials(match.team_two.name);
    card.querySelector(".score-one").textContent = match.score_one;
    card.querySelector(".score-two").textContent = match.score_two;
    card.querySelector(".format").textContent = match.best_of ? `Best of ${match.best_of}` : "Match";

    const stream = card.querySelector(".stream");
    if (match.stream_url) {
      stream.href = match.stream_url;
    } else {
      stream.remove();
    }

    if (match.winner_id === match.team_one.id) card.querySelector(".team-one").classList.add("winner");
    if (match.winner_id === match.team_two.id) card.querySelector(".team-two").classList.add("winner");

    const discuss = card.querySelector(".discuss");
    discuss.addEventListener("click", () => selectMatch(match));
    if (state.selectedMatch?.id === match.id) card.classList.add("selected");
    card.querySelector(".details-link").href = `/match/${encodeURIComponent(match.id)}`;

    matchList.append(card);
  }
}

function renderComments(comments) {
  commentList.innerHTML = "";
  discussionCount.textContent = String(comments.length);

  if (!comments.length) {
    const empty = document.createElement("p");
    empty.className = "empty-copy";
    empty.textContent = "No comments yet.";
    commentList.append(empty);
    return;
  }

  for (const comment of comments) {
    const item = document.createElement("article");
    item.className = "comment";
    const meta = document.createElement("div");
    meta.className = "comment-meta";
    meta.textContent = `${comment.author} / ${formatTime(comment.created_at)}${comment.updated_at ? " / edited" : ""}`;
    const body = document.createElement("p");
    body.textContent = comment.body;
    item.append(meta, body);
    if (comment.owned) {
      const actions = document.createElement("div");
      actions.className = "comment-actions";
      const edit = document.createElement("button");
      edit.type = "button";
      edit.textContent = "Edit";
      edit.addEventListener("click", () => editComment(comment));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Delete";
      remove.className = "danger-action";
      remove.addEventListener("click", () => deleteComment(comment));
      actions.append(edit, remove);
      item.append(actions);
    }
    commentList.append(item);
  }
}

async function editComment(comment) {
  const body = window.prompt("Edit comment", comment.body);
  if (body === null || !body.trim()) return;
  const response = await fetch(`/api/comments/${encodeURIComponent(comment.id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body: body.trim() }),
  });
  const payload = await response.json();
  if (!response.ok) {
    sourceNote.textContent = payload.error || "Could not edit comment";
    return;
  }
  await loadComments(state.selectedMatch.id);
}

async function deleteComment(comment) {
  if (!window.confirm("Delete this comment?")) return;
  const response = await fetch(`/api/comments/${encodeURIComponent(comment.id)}`, {
    method: "DELETE",
  });
  const payload = await response.json();
  if (!response.ok) {
    sourceNote.textContent = payload.error || "Could not delete comment";
    return;
  }
  await loadComments(state.selectedMatch.id);
}

async function loadComments(matchId) {
  const response = await fetch(`/api/matches/${encodeURIComponent(matchId)}/comments`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Could not load comments");
  renderComments(payload.comments);
}

async function selectMatch(match) {
  state.selectedMatch = match;
  discussionTitle.textContent = `${match.team_one.name} vs ${match.team_two.name}`;
  updateCommentComposer();
  document.querySelectorAll(".match-card").forEach((card) => {
    card.classList.toggle("selected", card.dataset.matchId === match.id);
  });

  try {
    await loadComments(match.id);
  } catch (error) {
    commentList.innerHTML = "";
    const message = document.createElement("p");
    message.className = "empty-copy";
    message.textContent = error.message;
    commentList.append(message);
  }
}

async function loadMatches() {
  sectionTitle.textContent = statusLabels[state.status];
  providerStatus.textContent = "Updating";
  refreshButton.disabled = true;

  try {
    const response = await fetch(`/api/matches?status=${state.status}&game=${state.game}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Score request failed");

    renderMatches(payload.matches);
    const source = payload.meta.mock ? "mock scores" : "PandaScore";
    providerStatus.textContent = source;
    sourceNote.textContent = `Updated ${formatTime(payload.meta.updated_at)} from ${source}.`;
  } catch (error) {
    providerStatus.textContent = "Error";
    sourceNote.textContent = error.message;
    renderMatches([]);
  } finally {
    refreshButton.disabled = false;
  }
}

function resetPolling() {
  window.clearInterval(state.timer);
  const refreshMs = state.status === "live" ? 30000 : 90000;
  state.timer = window.setInterval(loadMatches, refreshMs);
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabs.forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    state.status = tab.dataset.status;
    resetPolling();
    loadMatches();
  });
});

gameSelect.addEventListener("change", () => {
  state.game = gameSelect.value;
  loadMatches();
});

refreshButton.addEventListener("click", loadMatches);

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const mode = event.submitter?.dataset.mode || "login";
  const response = await fetch(`/api/auth/${mode}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: authUsername.value.trim(),
      password: authPassword.value,
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    sourceNote.textContent = payload.error || "Account request failed";
    return;
  }
  state.user = payload.user;
  authPassword.value = "";
  updateAuthUi();
  if (state.selectedMatch) await loadComments(state.selectedMatch.id);
});

logoutButton.addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  state.user = null;
  updateAuthUi();
  if (state.selectedMatch) await loadComments(state.selectedMatch.id);
});

commentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedMatch) return;

  const body = commentBody.value.trim();
  if (!body) return;

  const button = commentForm.querySelector("button");
  button.disabled = true;
  try {
    const response = await fetch(`/api/matches/${encodeURIComponent(state.selectedMatch.id)}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not post comment");
    commentBody.value = "";
    await loadComments(state.selectedMatch.id);
  } catch (error) {
    sourceNote.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

async function loadCurrentUser() {
  const response = await fetch("/api/auth/me");
  const payload = await response.json();
  state.user = payload.user;
  updateAuthUi();
}

loadCurrentUser();
resetPolling();
loadMatches();
