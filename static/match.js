const match = JSON.parse(document.querySelector("#matchData").textContent);
const state = { user: null };

const accountSummary = document.querySelector("#accountSummary");
const authForm = document.querySelector("#authForm");
const authUsername = document.querySelector("#authUsername");
const authPassword = document.querySelector("#authPassword");
const logoutButton = document.querySelector("#logoutButton");
const commentList = document.querySelector("#commentList");
const commentForm = document.querySelector("#commentForm");
const commentBody = document.querySelector("#commentBody");
const discussionCount = document.querySelector("#discussionCount");
const providerStatus = document.querySelector("#providerStatus");
const statsCoverage = document.querySelector("#statsCoverage");
const coverageNote = document.querySelector("#coverageNote");
const mapList = document.querySelector("#mapList");
const rosterGrid = document.querySelector("#rosterGrid");
const playerStatsWrap = document.querySelector("#playerStatsWrap");
const playerStatsCount = document.querySelector("#playerStatsCount");
const gridStatus = document.querySelector("#gridStatus");
const gridNote = document.querySelector("#gridNote");

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
  commentBody.disabled = !state.user;
  commentForm.querySelector("button").disabled = !state.user;
  commentBody.placeholder = state.user ? "Add a match comment" : "Login to comment";
}

function renderStats() {
  const stats = match.stats || {};
  statsCoverage.textContent = stats.detailed_stats ? "Detailed" : stats.available ? "Partial" : "Limited";
  coverageNote.textContent = stats.coverage_note || "No provider coverage note was returned.";
  renderMaps(stats.games || []);
  renderRosters(stats.rosters || []);
  renderPlayerStats(stats.player_stats || []);
  renderGrid(stats.grid || {});
}

function renderMaps(games) {
  mapList.innerHTML = "";
  if (!games.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No map/game records returned for this match.";
    mapList.append(empty);
    return;
  }

  for (const game of games) {
    const item = document.createElement("article");
    item.className = "map-item";
    const title = document.createElement("strong");
    title.textContent = `Game ${game.position || "?"}${game.map ? ` / ${game.map}` : ""}`;
    const meta = document.createElement("span");
    const bits = [
      game.status,
      game.winner_name ? `Winner: ${game.winner_name}` : null,
      game.length ? `Length: ${game.length}` : null,
      game.detailed_stats ? "Detailed stats" : null,
    ].filter(Boolean);
    meta.textContent = bits.join(" / ") || "No extra game data";
    item.append(title, meta);
    mapList.append(item);
  }
}

function renderRosters(rosters) {
  rosterGrid.innerHTML = "";
  if (!rosters.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No roster data returned.";
    rosterGrid.append(empty);
    return;
  }

  for (const roster of rosters) {
    const panel = document.createElement("article");
    panel.className = "roster-panel";
    const title = document.createElement("h3");
    title.textContent = roster.team_name;
    panel.append(title);
    if (!roster.players.length) {
      const empty = document.createElement("p");
      empty.className = "empty-copy";
      empty.textContent = "No players listed.";
      panel.append(empty);
    } else {
      const list = document.createElement("ul");
      for (const player of roster.players) {
        const item = document.createElement("li");
        item.textContent = `${player.name}${player.role ? ` / ${player.role}` : ""}`;
        list.append(item);
      }
      panel.append(list);
    }
    rosterGrid.append(panel);
  }
}

function renderPlayerStats(rows) {
  playerStatsCount.textContent = String(rows.length);
  playerStatsWrap.innerHTML = "";
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No player stat rows returned by the provider for this match.";
    playerStatsWrap.append(empty);
    return;
  }

  const metricKeys = [...new Set(rows.flatMap((row) => Object.keys(row.metrics || {})))].slice(0, 8);
  const table = document.createElement("table");
  table.className = "stats-table";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["Player", "Team", ...metricKeys].forEach((label) => {
    const cell = document.createElement("th");
    cell.textContent = label;
    headRow.append(cell);
  });
  head.append(headRow);
  table.append(head);

  const body = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    [row.player_name, row.team_name || "-", ...metricKeys.map((key) => row.metrics[key] ?? "-")].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = String(value);
      tr.append(cell);
    });
    body.append(tr);
  }
  table.append(body);
  playerStatsWrap.append(table);
}

function renderGrid(grid) {
  if (grid.raw) {
    gridStatus.textContent = "Connected";
    gridNote.textContent = grid.note || "GRID returned data for this match.";
  } else if (grid.configured) {
    gridStatus.textContent = "No data";
    gridNote.textContent = grid.note || "GRID is configured but did not return data for this match.";
  } else {
    gridStatus.textContent = "Not configured";
    gridNote.textContent = grid.note || "Set GRID_API_KEY and GRID_MATCH_DETAIL_URL_TEMPLATE to query GRID for CS/Dota.";
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

async function loadComments() {
  const response = await fetch(`/api/matches/${encodeURIComponent(match.id)}/comments`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Could not load comments");
  renderComments(payload.comments);
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
    providerStatus.textContent = payload.error || "Error";
    return;
  }
  await loadComments();
}

async function deleteComment(comment) {
  if (!window.confirm("Delete this comment?")) return;
  const response = await fetch(`/api/comments/${encodeURIComponent(comment.id)}`, { method: "DELETE" });
  const payload = await response.json();
  if (!response.ok) {
    providerStatus.textContent = payload.error || "Error";
    return;
  }
  await loadComments();
}

async function loadCurrentUser() {
  const response = await fetch("/api/auth/me");
  const payload = await response.json();
  state.user = payload.user;
  updateAuthUi();
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
    providerStatus.textContent = payload.error || "Account error";
    return;
  }
  state.user = payload.user;
  authPassword.value = "";
  updateAuthUi();
  await refreshMatch();
  await loadComments();
});

logoutButton.addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  state.user = null;
  updateAuthUi();
  await refreshMatch();
  await loadComments();
});

commentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = commentBody.value.trim();
  if (!body) return;
  const response = await fetch(`/api/matches/${encodeURIComponent(match.id)}/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  });
  const payload = await response.json();
  if (!response.ok) {
    providerStatus.textContent = payload.error || "Comment error";
    return;
  }
  commentBody.value = "";
  await loadComments();
});

async function refreshMatch() {
  const response = await fetch(`/api/matches/${encodeURIComponent(match.id)}`);
  const payload = await response.json();
  if (!response.ok) return;
  for (const button of document.querySelectorAll(".follow-button")) {
    const team = [payload.match.team_one, payload.match.team_two].find((item) => item.id === button.dataset.teamId);
    button.textContent = team?.followed ? "Following" : "Follow";
  }
}

document.querySelectorAll(".follow-button").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!state.user) {
      providerStatus.textContent = "Login first";
      return;
    }
    const following = button.textContent.trim() === "Following";
    const url = following ? `/api/follows/${encodeURIComponent(button.dataset.teamId)}` : "/api/follows";
    const options = following
      ? { method: "DELETE" }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            team_id: button.dataset.teamId,
            team_name: button.dataset.teamName,
            game: button.dataset.game,
          }),
        };
    const response = await fetch(url, options);
    const payload = await response.json();
    if (!response.ok) {
      providerStatus.textContent = payload.error || "Follow error";
      return;
    }
    button.textContent = following ? "Follow" : "Following";
  });
});

const detailStart = document.querySelector("#detailStart");
if (detailStart) detailStart.textContent = formatTime(detailStart.textContent);

renderStats();
loadCurrentUser();
loadComments();
