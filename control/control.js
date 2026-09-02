/* Agent HUD Control.
 *
 * The same gateway the glasses talk to, seen from a phone or a browser.
 * It uses the same endpoints and the same contract -- there are no
 * phone-only actions, and no second way to do anything.
 *
 * Two rules carried over from the glasses, for the same reasons:
 *
 *   Every action needs a confirmation step. Choosing one opens a
 *   question; only the confirm button sends.
 *
 *   Nothing claims an outcome it has not seen. "Sent" means the gateway
 *   accepted the request. When the work is actually done, the task
 *   changes in the list, and that is what says so.
 *
 * It also keeps nothing. No task text in localStorage, no offline copy
 * of anything, no analytics. The gateway is the only place this data
 * lives, which is the whole point of it being yours.
 */

"use strict";

const POLL_MS = 4000;

const state = {
  tasks: [],
  settings: null,
  online: false,
  draft: null, // whatever the gateway says is pending
  pending: null, // what the confirm dialog will do
  auth: null, // what the gateway says about signing in
};

// --- talking to the gateway -------------------------------------------

async function getJSON(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  return { status: response.status, payload };
}

async function postJSON(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  return { status: response.status, payload };
}

/* A fresh id for one answer, stable across retries of that same answer.
 * Random and nothing else: it reaches the gateway, so it must say nothing
 * about the person or the machine. */
function newRequestId() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

// --- signing in -------------------------------------------------------
//
// Passkeys. Your phone or laptop holds a private key and proves it holds
// it; what reaches the gateway is a public key and a signature. No
// password is typed, stored or sent, and no fingerprint or face ever
// leaves the device it was checked on -- the sensor unlocks the key
// locally, and the gateway is not even told that one was used.

const b64urlToBytes = (value) => {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
};

const bytesToB64url = (buffer) =>
  btoa(String.fromCharCode(...new Uint8Array(buffer)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");

/* The browser hands back ArrayBuffers; the gateway speaks base64url. */
function credentialToJSON(credential) {
  const r = credential.response;
  const out = {
    id: credential.id,
    rawId: bytesToB64url(credential.rawId),
    type: credential.type,
    clientExtensionResults: credential.getClientExtensionResults?.() ?? {},
    response: { clientDataJSON: bytesToB64url(r.clientDataJSON) },
  };
  if (r.attestationObject) {
    out.response.attestationObject = bytesToB64url(r.attestationObject);
  }
  if (r.authenticatorData) {
    out.response.authenticatorData = bytesToB64url(r.authenticatorData);
    out.response.signature = bytesToB64url(r.signature);
    if (r.userHandle) out.response.userHandle = bytesToB64url(r.userHandle);
  }
  return out;
}

function decodeOptions(options) {
  const decoded = { ...options, challenge: b64urlToBytes(options.challenge) };
  if (options.user) {
    decoded.user = { ...options.user, id: b64urlToBytes(options.user.id) };
  }
  for (const key of ["excludeCredentials", "allowCredentials"]) {
    if (Array.isArray(options[key])) {
      decoded[key] = options[key].map((c) => ({ ...c, id: b64urlToBytes(c.id) }));
    }
  }
  return decoded;
}

async function registerPasskey() {
  authSay("Follow the prompt on your device\u2026");
  try {
    const options = await getJSON("/auth/register/options");
    const credential = await navigator.credentials.create({
      publicKey: decodeOptions(options),
    });
    const result = await postJSON("/auth/register", {
      credential: credentialToJSON(credential),
      name: navigator.platform || "this device",
    });
    if (result.status !== 200) {
      authSay(result.payload.error || "That did not work.");
      return;
    }
    await signIn();
  } catch (error) {
    authSay(error?.message || "That did not work.");
  }
}

async function signIn() {
  authSay("Follow the prompt on your device\u2026");
  try {
    const options = await getJSON("/auth/login/options");
    const credential = await navigator.credentials.get({
      publicKey: decodeOptions(options),
    });
    const result = await postJSON("/auth/login", {
      credential: credentialToJSON(credential),
    });
    if (result.status !== 200) {
      authSay(result.payload.error || "That passkey was not accepted.");
      return;
    }
    await refresh();
  } catch (error) {
    authSay(error?.message || "That passkey was not accepted.");
  }
}

function authSay(message) {
  $("auth-body").textContent = message;
}

function renderAuth() {
  const card = $("auth-card");
  const auth = state.auth;

  // Nothing to show when the gateway is not asking, or already knows us.
  const needed = Boolean(auth?.required) && !auth?.signed_in;
  card.hidden = !needed;
  document.querySelectorAll("main > section:not(#auth-card)").forEach((s) => {
    s.hidden = needed || s.id === "pending-card" ? s.hidden : false;
  });
  if (needed) {
    document.querySelectorAll("main > section:not(#auth-card)").forEach((s) => {
      s.hidden = true;
    });
  }
  if (!needed) return;

  const buttons = $("auth-buttons");
  buttons.innerHTML = "";

  if (!auth.available) {
    authSay(
      "This gateway asks for a passkey but the library that checks one is " +
        'not installed. On the gateway: pip install ".[gateway]"',
    );
    return;
  }

  if (!auth.registered) {
    authSay(
      "No device is registered yet. Register this one to be the key for " +
        "this gateway. Nothing is typed and no password is stored.",
    );
    const register = el("button", "primary", "Register this device");
    register.addEventListener("click", registerPasskey);
    buttons.append(register);
    return;
  }

  authSay("Use your passkey to continue.");
  const button = el("button", "primary", "Sign in");
  button.addEventListener("click", signIn);
  buttons.append(button);
}

// --- drawing ----------------------------------------------------------

const $ = (id) => document.getElementById(id);

/* Which mark stands for which source. Chosen here from the source name,
 * exactly as the glasses do: the gateway never sends an image, so it can
 * never put arbitrary graphics on the screen. */
const MARKS = { claude: "✳", codex: "</>", github: "⑂" };
const markFor = (source) => MARKS[(source || "").trim().toLowerCase()] || "◯";

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function taskRow(task) {
  const row = el("div", "row tappable");
  row.tabIndex = 0;
  row.setAttribute("role", "button");

  const icon = el("span", "icon", markFor(task.source));
  icon.setAttribute("aria-hidden", "true");

  const body = el("div", "body");
  body.append(el("div", "name", task.source), el("div", "sub", task.summary));

  const chev = el("span", "chev", "›");
  chev.setAttribute("aria-hidden", "true");

  row.append(icon, body, chev);
  const open = () => openTask(task);
  row.addEventListener("click", open);
  row.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open();
    }
  });
  return row;
}

function renderStatus() {
  $("gw-name").textContent = state.settings?.gateway_name || "this machine";
  const gw = $("gw-state");
  gw.className = state.online ? "state" : "state bad";
  gw.innerHTML = "";
  gw.append(
    el("span", state.online ? "dot good" : "dot bad"),
    document.createTextNode(state.online ? "Online" : "Not answering"),
  );

  const seen = state.settings?.device_last_seen;
  const connected = Boolean(seen);
  const dev = $("device-state");
  dev.className = connected ? "state" : "state bad";
  dev.innerHTML = "";
  dev.append(
    el("span", connected ? "dot good" : "dot bad"),
    document.createTextNode(connected ? "Connected" : "Not seen"),
  );
  $("device-seen").textContent = seen ? relative(seen) : "never";

  const needs = state.tasks.filter((t) => t.needs_you).length;
  $("tile-needs").textContent = state.online ? String(needs) : "—";
  $("tile-drafts").textContent = state.draft ? "1" : "0";
}

function relative(epochSeconds) {
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - epochSeconds));
  if (seconds < 60) return "now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86400)} d ago`;
}

const VISIBLE_TASKS = 3;

function renderTasks() {
  const host = $("tasks");
  host.innerHTML = "";

  const waiting = state.tasks.filter((t) => t.needs_you);
  if (!waiting.length) {
    host.append(
      el(
        "div",
        "empty",
        state.online ? "Nothing is waiting on you." : "Cannot reach the gateway.",
      ),
    );
    $("tasks-more").textContent = "";
    return;
  }

  waiting.slice(0, VISIBLE_TASKS).forEach((task) => host.append(taskRow(task)));
  const extra = waiting.length - VISIBLE_TASKS;
  $("tasks-more").textContent = extra > 0 ? `+${extra} more` : "";
}

function renderSources() {
  const host = $("sources");
  host.innerHTML = "";
  const sources = state.settings?.sources || [];
  if (!sources.length) {
    host.append(el("div", "empty", "No sources reported."));
    return;
  }
  sources.forEach((source) => {
    const row = el("div", "row");
    const icon = el("span", "icon", markFor(source.name));
    icon.setAttribute("aria-hidden", "true");
    const body = el("div", "body");
    body.append(el("div", "name", source.label || source.name));

    const toggle = el("div", "toggle");
    toggle.setAttribute("role", "switch");
    toggle.setAttribute("aria-checked", String(Boolean(source.on)));
    toggle.setAttribute("aria-label", source.label || source.name);
    toggle.tabIndex = 0;
    // Reading only, for now: which feeders run is set where the gateway
    // is started. Showing it as changeable here would be a promise this
    // build cannot keep.
    toggle.style.opacity = ".55";
    toggle.style.cursor = "default";

    row.append(icon, body, toggle);
    host.append(row);
  });
}

function settingRow(label, value) {
  const row = el("div", "row");
  row.append(el("div", "body", "").appendChild(el("div", "name", label)).parentElement);
  row.append(el("span", "value-right", value));
  return row;
}

function renderSettings() {
  const host = $("settings");
  host.innerHTML = "";
  const s = state.settings;
  if (!s) {
    host.append(el("div", "empty", "Loading…"));
    return;
  }
  const interaction =
    s.interaction?.mode === "dwell"
      ? `Dwell, ${s.interaction.dwell_ms} ms`
      : "Double blink";
  host.append(settingRow("Interaction", interaction));
  host.append(settingRow("Auto-scroll", s.scroll?.auto ? "On" : "Off"));
  host.append(settingRow("Animations", s.display?.animations ? "On" : "Off"));
  host.append(settingRow("Audio language", s.audio?.language || "Auto"));

  const note = el(
    "div",
    "empty",
    "Looking at something never activates it. That is not a setting.",
  );
  note.style.marginTop = "10px";
  host.append(note);
}

function renderDraft() {
  const card = $("pending-card");
  card.hidden = !state.draft;
  if (state.draft) $("draft-text").value = state.draft.text;
}

function render() {
  renderAuth();
  if (state.auth?.required && !state.auth?.signed_in) return;
  renderStatus();
  renderTasks();
  renderSources();
  renderSettings();
  renderDraft();
}

// --- one task ---------------------------------------------------------

function openTask(task) {
  const dialog = $("task-dialog");
  $("dlg-title").textContent = task.title;
  $("dlg-source").textContent = task.source;
  $("dlg-detail").textContent = task.detail || "Nothing more to say about this one.";

  const actions = $("dlg-actions");
  actions.innerHTML = "";

  // Only what this gateway offered. Never anything invented here.
  ["primary", "secondary"].forEach((slot, index) => {
    const action = task.actions?.[slot];
    if (!action) return;
    const button = el("button", index === 0 ? "primary" : "", action.label);
    button.addEventListener("click", () => {
      dialog.close();
      askToConfirm(task, action);
    });
    actions.append(button);
  });

  const write = el("button", "", "Write response");
  write.addEventListener("click", async () => {
    dialog.close();
    // A draft with no words yet. It lives on the gateway like any other,
    // so it is the same thing the glasses would show.
    state.draft = {
      draft_id: null,
      task_id: task.id,
      revision: task.revision,
      text: "",
    };
    render();
    $("draft-text").focus();
  });
  actions.append(write);

  dialog.showModal();
}

/* Choosing an action never sends it. It opens this. */
function askToConfirm(task, action) {
  $("confirm-what").textContent = `${action.label} “${task.title}”?`;
  state.pending = {
    taskId: task.id,
    body: {
      revision: task.revision,
      type: "action",
      action_id: action.id,
      request_id: newRequestId(),
    },
    describe: action.label,
  };
  $("confirm-dialog").showModal();
}

function askToConfirmDraft() {
  const text = $("draft-text").value.trim();
  if (!text) return;
  $("confirm-what").textContent = "Send this response?";
  state.pending = {
    taskId: state.draft.task_id,
    draftId: state.draft.draft_id,
    body: {
      revision: state.draft.revision,
      type: "message",
      text,
      request_id: newRequestId(),
    },
    describe: "response",
    clearsDraft: true,
  };
  $("confirm-dialog").showModal();
}

async function discardDraft() {
  const draft = state.draft;
  state.draft = null;
  render();
  // A draft the gateway knows about has to be thrown away there too, or
  // it comes straight back on the next refresh -- and would still be on
  // the glasses.
  if (draft?.draft_id) {
    try {
      await post(`/drafts/${encodeURIComponent(draft.draft_id)}/discard`);
    } catch {
      /* it expires on its own soon enough */
    }
  }
  refresh();
}

/* The only place anything is transmitted. */
async function sendPending() {
  const pending = state.pending;
  if (!pending) return;
  state.pending = null;

  let result;
  try {
    // A draft the gateway is holding goes through its own door, so it is
    // marked sent there rather than left behind for the glasses to show.
    result = pending.draftId
      ? await post(`/drafts/${encodeURIComponent(pending.draftId)}/send`, {
          request_id: pending.body.request_id,
        })
      : await postJSON(
          `/tasks/${encodeURIComponent(pending.taskId)}/feedback`,
          pending.body,
        );
  } catch {
    // We do not know whether it arrived, so we do not say it did.
    say("Not sent. The gateway could not be reached — trying again is safe.");
    return;
  }

  if (result.status === 200) {
    if (pending.clearsDraft) state.draft = null;
    // "Sent" means the gateway took it. Not that the work is done.
    say("Sent. The gateway took your answer.");
  } else if (result.status === 409) {
    say("Not sent. This task changed while you were deciding — open it again.");
  } else {
    say(`Not sent. ${result.payload.error || "The gateway would not take it."}`);
  }
  await refresh();
}

function say(message) {
  const note = $("status-card");
  let line = note.querySelector(".notice");
  if (!line) {
    line = el("div", "empty notice");
    line.style.marginTop = "10px";
    note.append(line);
  }
  line.textContent = message;
}

// --- keeping up to date -----------------------------------------------

async function refresh() {
  try {
    state.auth = await getJSON("/auth/state");
  } catch {
    state.auth = null;
  }
  if (state.auth?.required && !state.auth?.signed_in) {
    state.online = false;
    render();
    return;
  }

  try {
    const [tasks, settings, drafts] = await Promise.all([
      getJSON("/tasks"),
      getJSON("/settings"),
      getJSON("/drafts"),
    ]);
    state.tasks = Array.isArray(tasks.tasks) ? tasks.tasks : [];
    state.settings = settings;
    // The gateway owns drafts, so a reply dictated into the glasses can
    // be finished here, and one typed here shows up there.
    const open = Array.isArray(drafts.drafts) ? drafts.drafts : [];
    const editing = document.activeElement === $("draft-text");
    if (!editing) state.draft = open[0] || null;
    state.online = true;
  } catch {
    // The last known list stays on screen, marked as not current. An
    // empty page would look exactly like "nothing needs you".
    state.online = false;
  }
  render();
}

$("refresh").addEventListener("click", refresh);
$("dlg-close").addEventListener("click", () => $("task-dialog").close());
$("confirm-cancel").addEventListener("click", () => {
  state.pending = null;
  $("confirm-dialog").close();
});
$("confirm-ok").addEventListener("click", () => {
  $("confirm-dialog").close();
  sendPending();
});
$("draft-send").addEventListener("click", askToConfirmDraft);
$("draft-discard").addEventListener("click", discardDraft);

refresh();
setInterval(refresh, POLL_MS);
