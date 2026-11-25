const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const $ = (id) => document.getElementById(id);
const user = tg.initDataUnsafe?.user; // for display only; the server verifies tg.initData

// ---- API helper: every request carries the signed initData
async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", Authorization: `tma ${tg.initData}` },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

function showError(err) {
  $("error").textContent = err.message || String(err);
  $("error").hidden = false;
}

// ---- render
let tasks = [];

function render() {
  const list = $("list");
  list.innerHTML = "";
  for (const t of tasks) {
    const li = document.createElement("li");
    li.className = t.done ? "done" : "";

    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = t.done;
    box.onchange = () => toggle(t, box.checked);

    const text = document.createElement("span");
    text.className = "text";
    text.textContent = t.text;

    const del = document.createElement("button");
    del.textContent = "×";
    del.ariaLabel = "Delete";
    del.onclick = () => remove(t);

    li.append(box, text, del);
    list.append(li);
  }
  const done = tasks.filter((t) => t.done).length;
  $("stats").textContent = `${done} of ${tasks.length} done`;
  $("empty").hidden = tasks.length > 0;
}

// ---- actions
async function load() {
  tasks = await api("GET", "/api/tasks");
  render();
}

async function add(text) {
  const t = await api("POST", "/api/tasks", { text });
  tasks.unshift(t);
  tg.HapticFeedback.impactOccurred("light");
  render();
}

async function toggle(t, done) {
  t.done = done;
  if (done) tg.HapticFeedback.notificationOccurred("success");
  render();
  await api("PATCH", `/api/tasks/${t.id}`, { done });
}

function remove(t) {
  tg.showConfirm(`Delete "${t.text}"?`, async (ok) => {
    if (!ok) return;
    tasks = tasks.filter((x) => x.id !== t.id);
    render();
    await api("DELETE", `/api/tasks/${t.id}`);
  });
}

// ---- Telegram's bottom MainButton adds the typed task
const input = $("new-task");
tg.MainButton.setText("Add task");

input.addEventListener("input", () => {
  input.value.trim() ? tg.MainButton.show() : tg.MainButton.hide();
});

async function submit() {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  tg.MainButton.hide();
  try { await add(text); } catch (e) { showError(e); }
}
tg.MainButton.onClick(submit);
$("add-form").addEventListener("submit", (e) => { e.preventDefault(); submit(); });

// ---- boot
if (user) {
  $("hello").textContent = `Hello, ${user.first_name}!`;
  if (user.photo_url) $("avatar").src = user.photo_url;
}
if (!tg.initData) {
  showError("Open this page from the Telegram bot, not a regular browser.");
} else {
  load().catch(showError);
}
