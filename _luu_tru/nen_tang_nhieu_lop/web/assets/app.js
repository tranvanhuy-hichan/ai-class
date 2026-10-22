// Giao diện nền tảng giám sát lớp học. Không dùng thư viện ngoài, chạy được không cần Internet.
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const B = ["phone", "head_down", "sleeping"];
const COLORS = { phone: "var(--phone)", head_down: "var(--head)", sleeping: "var(--sleep)" };
const SHORT = { phone: "Điện thoại", head_down: "Gục xuống bàn", sleeping: "Ngủ gật" };
const ICON = { phone: "i-phone", head_down: "i-down", sleeping: "i-moon" };
const STATE = { running: ["on", "Đang giám sát"], waiting: ["", "Chờ điện thoại"], starting: ["", "Đang kết nối"],
                error: ["alarm", "Lỗi camera"], off: ["", "Đang tắt"] };
const icon = (id, size = 14) => `<svg class="i" style="width:${size}px;height:${size}px"><use href="#${id}"/></svg>`;

let me = null, info = null, classes = [], today = {}, recent = [], lastId = 0, current = null;
let users = [], settings = {};

// ------------------------------------------------------------------ gọi API
async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  if (r.status === 401) { location.href = "/login"; throw new Error("Hết phiên đăng nhập"); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}
const send = (method, url, body) => api(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
const post = (url, body) => send("POST", url, body);
function msg(id, text, ok) { const el = $(id); el.textContent = text; el.className = "msg " + (ok ? "ok" : "err"); }
let toastTimer;
function toast(text) {
  $("toastText").textContent = text; $("toast").classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $("toast").classList.remove("show"), 4500);
}
const openModal = id => $(id).classList.add("open");
const closeModal = id => $(id).classList.remove("open");
const fmtTime = t => `${t.slice(11, 19)} · ${t.slice(8, 10)}/${t.slice(5, 7)}`;
const isAdmin = () => me?.role === "admin";

// ------------------------------------------------------------------ chuyển trang
const TITLES = { overview: "Tổng quan", class: "Lớp học", alerts: "Lịch sử cảnh báo", stats: "Thống kê", manage: "Quản lý" };
function route() {
  const [view, arg] = (location.hash.slice(1) || "overview").split("/");
  const v = TITLES[view] && (view !== "manage" || isAdmin()) ? view : "overview";
  document.querySelectorAll(".page").forEach(p => p.classList.toggle("active", p.id === "page-" + v));
  document.querySelectorAll(".nav").forEach(n => n.classList.toggle("active", n.dataset.view === v || (v === "class" && n.dataset.view === "overview")));
  $("title").textContent = TITLES[v];
  // Rời trang lớp -> ngắt luồng video để máy chủ đỡ tốn sức
  if (v !== "class" && current !== null) { $("cVideo").removeAttribute("src"); current = null; }
  if (v === "overview") renderOverview();
  if (v === "class") openClass(Number(arg));
  if (v === "alerts") { fillClassSelect("fClass"); loadAlerts(1); }
  if (v === "stats") { fillClassSelect("sClass"); loadStats(); }
  if (v === "manage") openTab(arg || "classes");
  $("menu").classList.remove("open");
}
addEventListener("hashchange", route);
document.addEventListener("click", e => { if (!$("menu").contains(e.target)) $("menu").classList.remove("open"); });

function fillClassSelect(id) {
  const el = $(id), val = el.value;
  el.innerHTML = `<option value="0">Tất cả lớp</option>` + classes.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  el.value = val || "0";
}

// ------------------------------------------------------------------ giao diện sáng/tối, đồng hồ
function renderTheme() { $("themeBtn").innerHTML = icon(document.documentElement.dataset.theme === "light" ? "i-moon" : "i-sun", 18); }
$("themeBtn").onclick = () => {
  const t = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("theme", t); } catch {}
  renderTheme();
};
setInterval(() => $("clock").textContent = new Date().toLocaleString("vi-VN",
  { weekday: "long", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }), 1000);

// ------------------------------------------------------------------ âm thanh
// Trình duyệt chỉ cho phát tiếng sau lần chạm/bấm đầu tiên vào trang.
const pref = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v === "1"; } catch { return d; } };
const savePref = (k, v) => { try { localStorage.setItem(k, v ? "1" : "0"); } catch {} };
let audioCtx, sound = pref("sound", true), voice = pref("voice", true);
function unlockAudio() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (audioCtx.state === "suspended") audioCtx.resume();
}
["click", "touchstart", "keydown"].forEach(ev => document.addEventListener(ev, unlockAudio, { once: true }));
const audioLocked = () => !audioCtx || audioCtx.state !== "running";
function renderSoundBtn() {
  const label = !sound ? "Tắt tiếng" : audioLocked() ? "Bấm để bật tiếng" : "Âm thanh bật";
  $("soundBtn").innerHTML = icon(sound ? "i-bell" : "i-bell-off", 18) + `<span class="hide-sm">${label}</span>`;
  $("soundBtn").classList.toggle("primary", sound && audioLocked());
}
$("soundBtn").onclick = () => {
  const wasLocked = audioLocked();
  unlockAudio();
  if (sound && wasLocked) { setTimeout(renderSoundBtn, 100); return; }
  sound = !sound; savePref("sound", sound); renderSoundBtn();
};
setInterval(renderSoundBtn, 1000);

const buffers = {};
function loadSound(url) {
  if (!(url in buffers)) buffers[url] = fetch(url).then(r => r.ok ? r.arrayBuffer() : Promise.reject())
    .then(b => audioCtx.decodeAudioData(b)).catch(() => null);
  return buffers[url];
}
async function playBuffer(buf) {
  const src = audioCtx.createBufferSource();
  src.buffer = buf; src.connect(audioCtx.destination); src.start();
  await new Promise(res => src.onended = res);
}
function beep(behavior) {
  const freq = { phone: 1000, head_down: 800, sleeping: 1300 }[behavior] || 1000;
  for (let i = 0; i < 2; i++) {
    const t = audioCtx.currentTime + i * 0.28, o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.frequency.value = freq; o.connect(g); g.connect(audioCtx.destination);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.35, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.2); o.start(t); o.stop(t + 0.22);
  }
}
// Chuông -> "Lớp 10A1" -> "Có học sinh dùng điện thoại". Phát lần lượt, không chồng tiếng.
let playing = Promise.resolve(), queued = 0;
function announce(classId, behavior) {
  if (queued >= 4) return;
  queued++;
  playing = playing.then(async () => {
    try {
      if (!voice) return beep(behavior);
      const parts = [await loadSound("/sounds/chime.wav")];
      if (classId) parts.push(await loadSound(`/voices/${classId}.wav`));
      parts.push(await loadSound(`/sounds/say_${behavior}.wav`));
      if (!parts[0] || !parts[parts.length - 1]) return beep(behavior);
      for (const b of parts) if (b) await playBuffer(b);
    } finally { queued--; }
  });
}
// Mở trang ngay trên máy chủ mà loa máy chủ đã bật -> trang không phát nữa (tránh nghe 2 lần)
const onServer = ["localhost", "127.0.0.1"].includes(location.hostname);
function alertSound(events) {
  if (!sound) return;
  if (onServer && settings.server_sound) return;
  if (audioLocked()) { toast("Bấm vào trang để bật âm thanh cảnh báo"); return; }
  const seen = new Set();
  for (const e of events) {
    const k = e.classroom_id + e.behavior;
    if (!seen.has(k)) { seen.add(k); announce(e.classroom_id, e.behavior); }
  }
}
function testVoice(b) { unlockAudio(); setTimeout(() => announce(classes[0]?.id, b), 100); }

// ------------------------------------------------------------------ cập nhật mỗi giây
async function poll() {
  try {
    const d = await api("/api/feed?after=" + lastId);
    classes = d.classes; today = d.today;
    if (d.events.length) {
      if (lastId) {
        toast([...new Set(d.events.map(e => `${e.class_name}: ${e.text}`))].join(" · "));
        alertSound(d.events);
      }
      recent.push(...d.events);
      recent = recent.slice(-300);
      lastId = d.events[d.events.length - 1].id;
    }
    const alarm = classes.filter(c => c.warning > 0).length;
    $("navCount").style.display = alarm ? "inline-block" : "none";
    $("navCount").textContent = alarm;
    if ($("page-overview").classList.contains("active")) renderOverview();
    if (current !== null) renderClassLive(d.events.length > 0);
  } catch (e) { /* mất kết nối tạm thời: thử lại ở lần sau */ }
}

// ------------------------------------------------------------------ TỔNG QUAN
function todayOf(id) { return today[id] || { phone: 0, head_down: 0, sleeping: 0 }; }
function renderOverview() {
  const tot = { phone: 0, head_down: 0, sleeping: 0 };
  for (const c of classes) for (const b of B) tot[b] += todayOf(c.id)[b];
  $("kRunning").textContent = classes.filter(c => c.state === "running").length + "/" + classes.length;
  const alarm = classes.filter(c => c.warning > 0).length;
  $("kAlarm").textContent = alarm;
  $("kAlarmCard").classList.toggle("alarm", alarm > 0);
  for (const b of B) $("k-" + b).textContent = tot[b];

  const grid = $("grid");
  if (!classes.length) {
    grid.innerHTML = isAdmin()
      ? `<div class="card empty-state" style="grid-column:1/-1"><div class="big">${icon("i-school", 30)}</div><h3>Chưa có lớp học nào</h3>
         <p>Thêm lớp đầu tiên và chọn camera cho lớp đó: webcam, điện thoại hoặc camera IP.</p>
         <button class="primary" onclick="openClassForm()">${icon("i-plus", 16)}Thêm lớp đầu tiên</button></div>`
      : `<div class="card empty-state" style="grid-column:1/-1"><div class="big">${icon("i-school", 30)}</div><h3>Bạn chưa được phân lớp nào</h3>
         <p>Hãy nhờ quản trị viên của trường thêm bạn vào lớp mình dạy.</p></div>`;
    return;
  }
  grid.querySelector(".empty-state")?.remove();
  const ids = new Set(classes.map(c => String(c.id)));
  grid.querySelectorAll(".cls").forEach(el => { if (!ids.has(el.dataset.id)) el.remove(); });
  for (const c of classes) {
    let el = grid.querySelector(`.cls[data-id="${c.id}"]`);
    if (!el) {
      el = document.createElement("a");
      el.className = "card cls"; el.dataset.id = c.id; el.href = `#class/${c.id}`;
      el.innerHTML = `<div class="shot"><img alt=""><div class="ov tl"><span class="chip"><span class="dot"></span><span class="st"></span></span></div>
        <div class="ov tr"><span class="chip ppl"></span></div><div class="warn"></div></div>
        <div class="body"><div><h3></h3><div class="state src"></div></div><div class="counts"></div></div>`;
      grid.appendChild(el);
    }
    const [dot, label] = STATE[c.state] || STATE.off;
    el.classList.toggle("alarm", c.warning > 0);
    el.querySelector(".ov.tl .dot").className = "dot " + (c.warning ? "alarm" : dot);
    el.querySelector(".st").textContent = c.state === "error" ? c.error : label;
    el.querySelector(".ppl").innerHTML = `${icon("i-users", 13)}${c.people}`;
    el.querySelector(".warn").textContent = c.announcements.join(" · ");
    el.querySelector("h3").textContent = c.name;
    el.querySelector(".src").textContent = c.source_label;
    const t = todayOf(c.id);
    el.querySelector(".counts").innerHTML = B.map(b => `<span class="tag c-${b}" title="${SHORT[b]} hôm nay">${icon(ICON[b], 12)}${t[b]}</span>`).join("");
  }
  if (isAdmin() && !grid.querySelector(".add-card")) {
    const add = document.createElement("button");
    add.className = "add-card"; add.innerHTML = `<div style="text-align:center">${icon("i-plus", 28)}<div style="margin-top:6px">Thêm lớp</div></div>`;
    add.onclick = () => openClassForm();
    grid.appendChild(add);
  }
  const add = grid.querySelector(".add-card");
  if (add) grid.appendChild(add);  // luôn nằm cuối
}
// Ảnh xem trước của từng lớp: làm mới mỗi 2 giây khi đang ở trang tổng quan
setInterval(() => {
  if (!$("page-overview").classList.contains("active") || document.hidden) return;
  $("grid").querySelectorAll(".cls").forEach(el => {
    el.querySelector("img").src = `/api/classes/${el.dataset.id}/thumb.jpg?t=${Date.now()}`;
  });
}, 2000);

// ------------------------------------------------------------------ 1 LỚP
async function openClass(id) {
  const c = classes.find(x => x.id === id);
  if (!c) { location.hash = "#overview"; return; }
  if (current !== id) {
    current = id;
    $("cVideo").src = `/api/classes/${id}/video`;
    $("cFeed").innerHTML = "";
    const from = new Date().toISOString().slice(0, 10);
    try {
      const d = await api(`/api/events?class_id=${id}&date_from=${from}&size=50`);
      $("cFeed").innerHTML = "";
      d.rows.reverse().forEach(addClassEvent);
    } catch {}
  }
  renderClassLive(false);
}
function renderClassLive(newEvents) {
  const c = classes.find(x => x.id === current);
  if (!c) return;
  $("title").textContent = "Lớp " + c.name;
  $("cName").textContent = c.name;
  $("cSource").textContent = c.state === "error" ? c.error : `${c.source_label} · ${(STATE[c.state] || STATE.off)[1]}`;
  $("cDot").className = "dot " + (c.warning ? "alarm" : (STATE[c.state] || STATE.off)[0]);
  $("cFps").textContent = c.fps + " FPS";
  $("stage").classList.toggle("alarm", c.warning > 0);
  $("cBanner").classList.toggle("show", c.announcements.length > 0);
  $("cBannerText").textContent = c.announcements.join(" · ");
  const t = todayOf(c.id);
  for (const b of B) $("c-" + b).innerHTML = `${icon(ICON[b], 12)}${t[b]}`;
  if (newEvents) recent.filter(e => e.classroom_id === current && !$("cFeed").querySelector(`[data-ev="${e.id}"]`)).forEach(addClassEvent);
  if (!$("cFeed").children.length) $("cFeed").innerHTML = `<div class="empty"><div class="big">${icon("i-check", 26)}</div>Chưa có cảnh báo hôm nay<br><span class="hint">Lớp học đang trật tự</span></div>`;
}
function addClassEvent(e) {
  const feed = $("cFeed");
  feed.querySelector(".empty")?.remove();
  const div = document.createElement("div");
  div.className = "ev c-" + e.behavior; div.dataset.ev = e.id;
  div.innerHTML = `${e.snapshot ? `<img src="${e.snapshot}" alt="" onclick="zoom('${e.snapshot}')">` : ""}
    <div style="min-width:0"><span class="tag">${icon(ICON[e.behavior], 12)}${esc(SHORT[e.behavior])}</span>
    <div class="who" style="margin-top:6px">${esc(e.text)}</div><div class="meta">${fmtTime(e.time)} · kéo dài ${Math.round(e.duration)}s</div></div>`;
  feed.prepend(div);
}
function zoom(src) { $("bigImg").src = src; openModal("imgModal"); }
function fullscreen() { document.fullscreenElement ? document.exitFullscreen() : $("stage").requestFullscreen?.(); }

// ------------------------------------------------------------------ LỊCH SỬ CẢNH BÁO
let aPage = 1;
function alertQuery() {
  const q = new URLSearchParams({ class_id: $("fClass").value, behavior: $("fBehavior").value, date_from: $("fFrom").value, date_to: $("fTo").value });
  return q.toString();
}
async function loadAlerts(page) {
  aPage = page;
  const d = await api(`/api/events?${alertQuery()}&page=${page}&size=30`).catch(() => null);
  if (!d) return;
  $("aBody").innerHTML = d.rows.length ? d.rows.map(e => `<tr>
      <td>${e.snapshot ? `<img src="${e.snapshot}" alt="" onclick="zoom('${e.snapshot}')">` : ""}</td>
      <td>${fmtTime(e.time)}</td><td><b>${esc(e.class_name)}</b></td>
      <td><span class="tag c-${e.behavior}">${icon(ICON[e.behavior], 12)}${SHORT[e.behavior]}</span></td>
      <td class="muted">#${e.student}</td><td class="num">${Math.round(e.duration)}s</td></tr>`).join("")
    : `<tr><td colspan="6" class="muted" style="text-align:center;padding:40px">Không có cảnh báo nào</td></tr>`;
  const pages = Math.max(1, Math.ceil(d.total / 30));
  $("aPager").innerHTML = `${d.total} cảnh báo · trang ${page}/${pages}
    <button ${page <= 1 ? "disabled" : ""} onclick="loadAlerts(${page - 1})">‹ Trước</button>
    <button ${page >= pages ? "disabled" : ""} onclick="loadAlerts(${page + 1})">Sau ›</button>`;
}
function exportCsv() { location.href = `/api/events.csv?${alertQuery()}`; }

// ------------------------------------------------------------------ THỐNG KÊ
function stackedBars(el, axisEl, rows, every) {
  const max = Math.max(1, ...rows.map(r => B.reduce((a, b) => a + r[b], 0)));
  el.innerHTML = rows.map(r => {
    const tot = B.reduce((a, b) => a + r[b], 0);
    const segs = tot ? B.filter(b => r[b]).map(b => `<div style="height:${r[b] / max * 100}%;background:${COLORS[b]}"></div>`).join("") : `<div class="stub"></div>`;
    return `<div class="bar" data-tip="${r.label}: ${r.phone} điện thoại · ${r.head_down} gục bàn · ${r.sleeping} ngủ gật">${segs}</div>`;
  }).join("");
  axisEl.innerHTML = rows.filter((_, i) => i % every === 0 || i === rows.length - 1).map(r => `<span>${r.label}</span>`).join("");
}
async function loadStats() {
  const days = Number($("sDays").value);
  const s = await api(`/api/stats?days=${days}&class_id=${$("sClass").value}`).catch(() => null);
  if (!s) return;
  $("legend1").innerHTML = B.map(b => `<span><i style="background:${COLORS[b]}"></i>${SHORT[b]}</span>`).join("");
  stackedBars($("chDay"), $("axDay"), s.by_day, Math.ceil(s.by_day.length / 7));
  stackedBars($("chHour"), $("axHour"), s.by_hour, 3);
  const sum = B.reduce((a, b) => a + s.totals[b], 0);
  let acc = 0;
  const stops = B.map(b => { const a = acc; acc += sum ? s.totals[b] / sum * 360 : 0; return `${COLORS[b]} ${a}deg ${acc}deg`; });
  $("donut").style.background = sum ? `conic-gradient(${stops.join(",")})` : "var(--surface-3)";
  $("donutTotal").textContent = sum;
  $("donutRows").innerHTML = B.map(b => `<div class="r"><span class="tag c-${b}">${icon(ICON[b], 12)}${SHORT[b]}</span>
      <span class="n">${s.totals[b]}</span><span class="muted" style="width:44px;text-align:right">${sum ? Math.round(s.totals[b] / sum * 100) : 0}%</span></div>`).join("");
  const maxC = Math.max(1, ...s.by_class.map(c => B.reduce((a, b) => a + c[b], 0)));
  $("byClass").innerHTML = s.by_class.length ? s.by_class.map(c => {
    const t = B.reduce((a, b) => a + c[b], 0);
    return `<div class="hbar"><b>${esc(c.name)}</b><div class="track" style="width:${t / maxC * 100}%">${B.map(b => `<div style="width:${c[b] / t * 100}%;background:${COLORS[b]}" title="${SHORT[b]}: ${c[b]}"></div>`).join("")}</div><span class="muted">${t}</span></div>`;
  }).join("") : `<div class="muted" style="text-align:center;padding:30px">Chưa có dữ liệu</div>`;
}

// ------------------------------------------------------------------ QUẢN LÝ: tab
function openTab(tab) {
  document.querySelectorAll("#mTabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
  for (const t of ["classes", "users", "settings"]) $("tab-" + t).style.display = t === tab ? "" : "none";
  if (tab === "classes") loadManageClasses();
  if (tab === "users") loadUsers();
  if (tab === "settings") loadSettings();
}
document.querySelectorAll("#mTabs button").forEach(b => b.onclick = () => location.hash = "#manage/" + b.dataset.tab);

// ------------------------------------------------------------------ QUẢN LÝ: lớp
async function loadManageClasses() {
  users = await api("/api/users").catch(() => users);
  const teachersOf = id => users.filter(u => u.role === "teacher" && u.class_ids.includes(id)).map(u => esc(u.name));
  $("mClasses").innerHTML = classes.length ? classes.map(c => {
    const [dot, label] = STATE[c.state] || STATE.off;
    return `<tr><td><b>${esc(c.name)}</b></td><td>${esc(c.source_label)}</td>
      <td><span class="state"><span class="dot ${dot}"></span>${esc(c.state === "error" ? c.error : label)}</span></td>
      <td>${teachersOf(c.id).map(n => `<span class="pill">${n}</span>`).join("") || '<span class="muted">-</span>'}</td>
      <td><div class="actions">
        ${c.source === "phone" ? `<button class="ghost icon" title="Mã QR cho điện thoại" onclick="showStationQR(${c.id})">${icon("i-qr", 16)}</button>` : ""}
        <button class="ghost icon" title="Sửa" onclick="openClassForm(${c.id})">${icon("i-edit", 16)}</button>
        <button class="ghost icon danger" title="Xoá" onclick="deleteClass(${c.id})">${icon("i-trash", 16)}</button></div></td></tr>`;
  }).join("") : `<tr><td colspan="5" class="muted" style="text-align:center;padding:30px">Chưa có lớp nào. Bấm “Thêm lớp”.</td></tr>`;
}

let cfEditing = null, cfType = "webcam";
function setSourceType(t) {
  cfType = t;
  document.querySelectorAll("#cfType button").forEach(b => b.classList.toggle("on", b.dataset.type === t));
  document.querySelectorAll("#classModal [data-for]").forEach(r => r.style.display = r.dataset.for === t ? "" : "none");
}
document.querySelectorAll("#cfType button").forEach(b => b.onclick = () => setSourceType(b.dataset.type));

async function openClassForm(id) {
  const c = id ? classes.find(x => x.id === id) : null;
  cfEditing = c ? c.id : null;
  $("cfTitle").textContent = c ? `Sửa lớp ${c.name}` : "Thêm lớp";
  $("cfName").value = c?.name || "";
  $("cfChat").value = c?.telegram_chat_id || "";
  $("cfEnabled").checked = c ? c.enabled : true;
  $("cfUrl").value = ""; $("cfFile").value = "";
  $("cfMsg").textContent = "";
  const src = c?.source || "";
  setSourceType(!c ? "webcam" : src === "phone" ? "phone" : /^\d+$/.test(src) ? "webcam" : src.includes("://") ? "ip" : src ? "video" : "webcam");
  if (cfType === "ip") $("cfUrl").value = src;
  $("cfVideoHint").textContent = cfType === "video" && src ? "Đang dùng: " + c.source_label + ". Chọn file mới nếu muốn đổi." : "";
  $("cfPhoneHint").innerHTML = "Sau khi lưu, bấm biểu tượng " + icon("i-qr", 13) + " ở danh sách lớp để lấy mã QR. Dùng điện thoại <b>cùng Wi-Fi</b> quét mã, bấm <b>Bắt đầu</b>, rồi đặt điện thoại cố định hướng về phía học sinh.";
  $("cfWebcam").innerHTML = `<option>Đang tìm webcam...</option>`;
  openModal("classModal");
  const cams = await api("/api/cameras").catch(() => []);
  $("cfWebcam").innerHTML = (cams.length ? cams : [0]).map(i => `<option value="${i}">Webcam ${i}${i === 0 ? " (camera của máy)" : ""}</option>`).join("");
  if (/^\d+$/.test(src)) $("cfWebcam").value = src;
}
async function saveClass() {
  const body = { name: $("cfName").value.trim(), enabled: $("cfEnabled").checked, telegram_chat_id: $("cfChat").value.trim() };
  const old = classes.find(x => x.id === cfEditing);
  body.source = { webcam: $("cfWebcam").value, phone: "phone", ip: $("cfUrl").value.trim(), video: old?.source || "" }[cfType];
  if (!body.name) return msg("cfMsg", "Hãy nhập tên lớp");
  if (cfType === "ip" && !body.source) return msg("cfMsg", "Hãy nhập địa chỉ camera");
  const file = $("cfFile").files[0];
  if (cfType === "video" && !file && !(old && !/^\d+$/.test(old.source) && !old.source.includes("://") && old.source !== "phone")) return msg("cfMsg", "Hãy chọn file video");
  $("cfSave").disabled = true;
  try {
    const r = cfEditing ? await send("PUT", `/api/classes/${cfEditing}`, body) : await post("/api/classes", body);
    if (cfType === "video" && file) {
      msg("cfMsg", "Đang tải video lên...", true);
      const fd = new FormData(); fd.append("file", file);
      await api(`/api/classes/${r.id}/upload`, { method: "POST", body: fd });
    }
    closeModal("classModal");
    await poll();
    if ($("page-manage").classList.contains("active")) loadManageClasses();
    toast(`Đã lưu lớp ${body.name}`);
    if (cfType === "phone") setTimeout(() => showStationQR(r.id), 300);
  } catch (e) { msg("cfMsg", e.message); }
  finally { $("cfSave").disabled = false; }
}
async function deleteClass(id) {
  const c = classes.find(x => x.id === id);
  if (!confirm(`Xoá lớp ${c.name}? Toàn bộ lịch sử cảnh báo và ảnh của lớp này sẽ bị xoá.`)) return;
  await send("DELETE", `/api/classes/${id}`).catch(e => toast(e.message));
  await poll(); loadManageClasses();
}
function showStationQR(id) {
  const c = classes.find(x => x.id === id);
  if (!c?.station_url) return toast("Chưa bật HTTPS nên chưa dùng được camera điện thoại");
  $("qrTitle").textContent = `Camera điện thoại · Lớp ${c.name}`;
  $("qrImg").src = "/api/qr?url=" + encodeURIComponent(c.station_url);
  $("qrUrl").textContent = c.station_url;
  $("qrHint").innerHTML = "Quét bằng điện thoại <b>cùng Wi-Fi</b> → bấm <b>Bắt đầu</b>.<br>Trình duyệt báo “không an toàn” thì chọn <i>Nâng cao → Tiếp tục</i> (chứng chỉ tự tạo trong mạng nội bộ).<br>Ai có mã này đều gửi được hình cho lớp, đừng chia sẻ ra ngoài.";
  openModal("qrModal");
}

// ------------------------------------------------------------------ QUẢN LÝ: giáo viên
async function loadUsers() {
  users = await api("/api/users").catch(() => []);
  const name = id => esc(classes.find(c => c.id === id)?.name || "?");
  $("mUsers").innerHTML = users.map(u => `<tr><td><b>${esc(u.name)}</b>${u.id === me.id ? ' <span class="pill">bạn</span>' : ""}</td>
    <td>${esc(u.username)}</td><td>${u.role === "admin" ? '<span class="tag" style="--c:var(--accent)">Quản trị</span>' : "Giáo viên"}</td>
    <td>${u.role === "admin" ? '<span class="muted">Tất cả</span>' : u.class_ids.map(id => `<span class="pill">${name(id)}</span>`).join("") || '<span class="muted">Chưa phân lớp</span>'}</td>
    <td><div class="actions"><button class="ghost icon" title="Sửa" onclick="openUserForm(${u.id})">${icon("i-edit", 16)}</button>
      ${u.id !== me.id ? `<button class="ghost icon danger" title="Xoá" onclick="deleteUser(${u.id})">${icon("i-trash", 16)}</button>` : ""}</div></td></tr>`).join("");
}
let ufEditing = null;
function openUserForm(id) {
  const u = id ? users.find(x => x.id === id) : null;
  ufEditing = u ? u.id : null;
  $("ufTitle").textContent = u ? `Sửa tài khoản ${u.name}` : "Thêm giáo viên";
  $("ufName").value = u?.name || ""; $("ufUsername").value = u?.username || ""; $("ufUsername").disabled = !!u;
  $("ufPassword").value = ""; $("ufPwLabel").textContent = u ? "Đặt lại mật khẩu (để trống nếu không đổi)" : "Mật khẩu";
  $("ufRole").value = u?.role || "teacher";
  $("ufClasses").innerHTML = classes.length ? classes.map(c => `<label><input type="checkbox" value="${c.id}" ${u?.class_ids.includes(c.id) ? "checked" : ""}>${esc(c.name)}</label>`).join("")
    : `<span class="muted">Chưa có lớp nào</span>`;
  $("ufRole").onchange = () => $("ufClassesRow").style.display = $("ufRole").value === "admin" ? "none" : "";
  $("ufRole").onchange();
  $("ufMsg").textContent = "";
  openModal("userModal");
}
async function saveUser() {
  const body = { name: $("ufName").value.trim(), username: $("ufUsername").value.trim(), password: $("ufPassword").value,
                 role: $("ufRole").value, class_ids: [...$("ufClasses").querySelectorAll("input:checked")].map(i => Number(i.value)) };
  if (!body.name) return msg("ufMsg", "Hãy nhập họ tên");
  try {
    if (ufEditing) await send("PUT", `/api/users/${ufEditing}`, body); else await post("/api/users", body);
    closeModal("userModal"); loadUsers();
    toast(ufEditing ? "Đã lưu thay đổi" : `Đã tạo tài khoản ${body.username}. Gửi tên đăng nhập và mật khẩu cho giáo viên nhé.`);
  } catch (e) { msg("ufMsg", e.message); }
}
async function deleteUser(id) {
  const u = users.find(x => x.id === id);
  if (!confirm(`Xoá tài khoản ${u.name}?`)) return;
  await send("DELETE", `/api/users/${id}`).catch(e => toast(e.message));
  loadUsers();
}

// ------------------------------------------------------------------ QUẢN LÝ: cài đặt
const NUM_KEYS = ["head_down_ratio", "phone_seconds", "head_down_seconds", "sleeping_seconds", "cooldown", "imgsz", "fps_background", "fps_watch", "keep_days"];
async function loadSettings() {
  settings = await api("/api/settings").catch(() => settings);
  for (const k of NUM_KEYS) $(k).value = settings[k];
  $("v-head_down_ratio").textContent = settings.head_down_ratio;
  $("server_sound").checked = settings.server_sound; $("save_snapshots").checked = settings.save_snapshots;
  $("telegram_token").value = settings.telegram_token; $("telegram_chat_id").value = settings.telegram_chat_id;
  $("pageSound").checked = sound; $("voiceChk").checked = voice;
}
$("head_down_ratio").oninput = e => $("v-head_down_ratio").textContent = e.target.value;
$("pageSound").onchange = e => { sound = e.target.checked; savePref("sound", sound); unlockAudio(); renderSoundBtn(); };
$("voiceChk").onchange = e => { voice = e.target.checked; savePref("voice", voice); };
async function saveSettings() {
  const body = Object.fromEntries(NUM_KEYS.map(k => [k, $(k).value]));
  Object.assign(body, { server_sound: $("server_sound").checked, save_snapshots: $("save_snapshots").checked,
                        telegram_token: $("telegram_token").value, telegram_chat_id: $("telegram_chat_id").value });
  try { settings = await post("/api/settings", body); msg("setMsg", "✔ Đã lưu, áp dụng ngay cho mọi lớp", true); }
  catch (e) { msg("setMsg", e.message); }
}
async function findChat(inputId, msgId) {
  try {
    const r = await post("/api/telegram/find-chat", { token: $("telegram_token").value || settings.telegram_token });
    $(inputId).value = r.chat_id; msg(msgId, `✔ Tìm thấy: ${r.name} (${r.chat_id}). Nhớ bấm Lưu.`, true);
  } catch (e) { msg(msgId, e.message); }
}
async function testTelegram() {
  await saveSettings();
  try { await post("/api/telegram/test", {}); msg("tgMsg", "✔ Đã gửi, kiểm tra Telegram nhé", true); }
  catch (e) { msg("tgMsg", e.message); }
}

// ------------------------------------------------------------------ tài khoản
function openPassword() { $("pwOld").value = $("pwNew").value = ""; $("pwMsg").textContent = ""; openModal("pwModal"); }
async function changePassword() {
  try { await post("/api/me/password", { old: $("pwOld").value, new: $("pwNew").value }); closeModal("pwModal"); toast("Đã đổi mật khẩu"); }
  catch (e) { msg("pwMsg", e.message); }
}
async function logout() { await post("/api/logout").catch(() => {}); location.href = "/login"; }
function openQR() {
  if (!info) return;
  $("qrTitle").textContent = "Mở trên điện thoại";
  $("qrImg").src = "/api/qr?url=" + encodeURIComponent(info.urls.lan);
  $("qrUrl").textContent = info.urls.lan;
  $("qrHint").innerHTML = "Điện thoại phải dùng cùng mạng Wi-Fi với máy chủ.<br>Không mở được? Trên máy chủ Windows, khi có hộp thoại tường lửa hãy chọn <b>Allow</b>.";
  openModal("qrModal");
}

// ------------------------------------------------------------------ khởi động
(async function init() {
  me = await api("/api/me");
  info = await api("/api/info").catch(() => null);
  if (isAdmin()) settings = await api("/api/settings").catch(() => ({}));
  document.querySelectorAll(".admin-only").forEach(el => el.style.display = isAdmin() ? "" : "none");
  $("avatar").textContent = (me.name || me.username).trim().split(/\s+/).pop()[0].toUpperCase();
  $("whoName").textContent = me.name; $("menuName").textContent = me.name;
  $("menuRole").textContent = (isAdmin() ? "Quản trị viên" : "Giáo viên") + " · " + me.username;
  $("footUrl").textContent = info?.urls.lan || "-";
  renderTheme(); renderSoundBtn();
  await poll();
  route();
  setInterval(poll, 1000);
})();
