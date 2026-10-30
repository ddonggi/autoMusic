"use strict";
const $ = (id) => document.getElementById(id);
const state = { categories: [], preview: null, pending: null, busy: false, previewBusy: false, sequence: 0, library: [], libraryBusy: false, libraryError: null, libraryLoaded: false, scheduler: null, schedulerBusy: false, jobsBusy: false };
const labels = { queued: "대기 중", generating_music: "음악 생성 중", completed: "완료", failed: "실패", interrupted: "재시작으로 중단" };
const active = (job) => ["queued", "generating_music"].includes(job.status);
const text = (id, value) => { if ($(id).textContent !== String(value)) $(id).textContent = value; };
function element(tag, content, className) {
  const node = document.createElement(tag);
  if (content != null) node.textContent = content;
  if (className) node.className = className;
  return node;
}
function safeURL(value) {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) return null;
  try { const url = new URL(value, location.origin); return url.origin === location.origin && url.pathname.startsWith("/api/") ? url.href : null; } catch { return null; }
}
function dateLabel(value) {
  if (!value) return "시각 정보 없음";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "시각 정보 없음" : date.toLocaleString("ko-KR");
}
function duration(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "길이 정보 없음";
  const seconds = Math.round(value);
  return `${Math.floor(seconds / 60)}분 ${seconds % 60}초`;
}
function elapsed(job) {
  if (!active(job) || !job.started_at) return "";
  const start = Date.parse(job.started_at);
  return Number.isFinite(start) ? ` · 경과 ${duration(Math.max(0, (Date.now() - start) / 1000))}` : "";
}
async function api(path, body) {
  let response;
  try {
    response = await fetch(path, { method: body === undefined ? "GET" : "POST", credentials: "same-origin", headers: body === undefined ? {} : { "Content-Type": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  } catch { throw new Error("연결하지 못했습니다. 마지막으로 확인한 내용을 표시합니다."); }
  let data;
  try { data = await response.json(); } catch { throw new Error("응답을 확인하지 못했습니다. 상태를 다시 확인하세요."); }
  if (!response.ok) {
    const error = new Error(typeof data.error === "string" ? data.error : "요청을 처리하지 못했습니다.");
    error.definitive = response.status >= 400 && response.status < 500;
    error.data = data;
    throw error;
  }
  if (!data || typeof data !== "object") throw new Error("응답 형식을 확인할 수 없습니다.");
  return data;
}
function items(data) { if (!Array.isArray(data.items)) throw new Error("목록 응답을 확인할 수 없습니다."); return data.items; }
function skipToContent(event) {
  event.preventDefault();
  $("content").focus();
}
let playingAudio = null;
let currentView = null;
function stopPlayback(reset = false) {
  if (!playingAudio) return;
  playingAudio.pause();
  if (reset) playingAudio.currentTime = 0;
  playingAudio = null;
}
function route() {
  const ids = ["dashboard", "generate", "library", "scheduler"];
  const name = ids.includes(location.hash.slice(1)) ? location.hash.slice(1) : "dashboard";
  if (name !== currentView) {
    stopPlayback(true);
    currentView = name;
  }
  ids.forEach((id) => { $(id).hidden = id !== name; });
  document.querySelectorAll(".navigation a").forEach((link) => {
    if (link.hash === `#${name}`) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  });
  if (name === "library") loadLibrary();
}
function detailLabel(value) {
  if (value == null) return "";
  if (Array.isArray(value)) return value.map(detailLabel).filter(Boolean).join(", ");
  if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key}: ${detailLabel(item)}`).join(" · ");
  return String(value);
}
function controls() {
  const locked = state.busy || Boolean(state.pending);
  $("category").disabled = locked || !state.categories.length || state.previewBusy;
  $("variant").disabled = locked || !$("category").value || state.previewBusy;
  $("preview").disabled = locked || !$("category").value || state.previewBusy;
  $("reload-categories").disabled = locked || state.previewBusy;
  $("music-prompt").disabled = locked || !state.preview || state.previewBusy;
  $("create-job").disabled = locked || !state.preview || state.previewBusy || !$("music-prompt").value.trim();
  $("retry-submit").hidden = !state.pending || Boolean(state.pending.jobId);
  $("retry-submit").disabled = state.busy;
}
function savePending() {
  try { if (state.pending) sessionStorage.setItem("automusic.pending", JSON.stringify(state.pending)); else sessionStorage.removeItem("automusic.pending"); } catch { /* Same-page idempotency remains available when storage is blocked. */ }
}
function invalidatePreview() { state.preview = null; state.sequence += 1; $("music-prompt").value = ""; text("preview-details", "미리보기를 다시 확인하세요."); if (!state.pending) text("job-status", "미리보기를 먼저 확인하세요."); controls(); }
function hasEdits() { return state.preview && $("music-prompt").value !== state.preview.prompt; }
function confirmDiscard() { return !hasEdits() || window.confirm("수정한 프롬프트를 지우고 선택을 바꿀까요?"); }
let selectedCategory = "";
let selectedVariant = "random";
function fillVariants() {
  const category = state.categories.find((item) => item.id === $("category").value);
  $("variant").replaceChildren(new Option("랜덤으로 선택", "random"));
  (category?.variants || []).forEach((variant) => $("variant").add(new Option(variant.label || variant.id, variant.id)));
  selectedVariant = "random";
}
async function loadCategories() {
  if (state.pending || state.busy) return;
  if (!confirmDiscard()) return;
  invalidatePreview();
  $("category").disabled = true; $("reload-categories").disabled = true;
  text("selection-message", "선택지를 불러오는 중입니다.");
  try {
    const categories = items(await api("/api/categories"));
    state.categories = categories.filter((item) => typeof item.id === "string" && Array.isArray(item.variants));
    $("category").replaceChildren(new Option("직접 선택하세요", ""));
    state.categories.forEach((category) => $("category").add(new Option(category.label || category.id, category.id)));
    selectedCategory = ""; fillVariants();
    text("selection-message", state.categories.length ? "카테고리는 직접, 변형은 직접 또는 랜덤으로 고르세요." : "사용할 수 있는 카테고리가 없습니다.");
  } catch (error) { state.categories = []; text("selection-message", error.message); }
  finally { controls(); }
}
async function preview() {
  if (state.previewBusy || state.pending || !$("category").value || !confirmDiscard()) return;
  const sequence = ++state.sequence;
  state.previewBusy = true; controls(); text("selection-message", "선택한 변형과 프롬프트를 확인하는 중입니다.");
  try {
    const result = await api("/api/previews", { category_id: $("category").value, variant_id: $("variant").value });
    if (sequence !== state.sequence) return;
    if (!result.id || typeof result.prompt !== "string" || result.category_id !== $("category").value) throw new Error("미리보기 응답을 확인할 수 없습니다.");
    state.preview = result; $("music-prompt").value = result.prompt;
    const details = result.details || {};
    const list = [result.category_id, result.variant_id || "기본형", result.model, details.genre, details.bpm != null ? `${details.bpm} BPM` : null, details.instruments, details.mood, details.arrangement, details.duration_seconds != null ? `설정 길이 ${duration(details.duration_seconds)}` : null];
    text("preview-details", list.map(detailLabel).filter(Boolean).join(" · "));
    text("selection-message", "이 변형으로 만듭니다. 음악을 만들 때 다시 뽑지 않습니다.");
    if (!state.pending) text("job-status", "확인한 프롬프트로 음악을 만들 준비가 됐습니다.");
    text("form-error", ""); $("new-draft").hidden = true;
  } catch (error) { if (sequence === state.sequence) { state.preview = null; text("selection-message", error.message); } }
  finally { state.previewBusy = false; controls(); }
}
async function createJob() {
  if (state.busy || state.pending || !state.preview) return;
  const prompt = $("music-prompt").value.trim();
  if (!prompt) { text("form-error", "프롬프트를 입력하세요."); $("music-prompt").focus(); return; }
  state.pending = { body: { preview_id: state.preview.id, music_prompt: prompt, request_id: crypto.randomUUID() }, jobId: null };
  savePending(); await submitPending();
}
async function submitPending() {
  if (state.busy || !state.pending || state.pending.jobId) return;
  state.busy = true; controls(); text("form-error", ""); text("job-status", "요청을 접수하고 있습니다.");
  try {
    const job = await api("/api/jobs", state.pending.body);
    if (!job.id || !job.status) throw new Error("접수 결과를 확인할 수 없습니다.");
    state.pending.jobId = job.id; savePending();
    text("job-status", labels[job.status] || "알 수 없는 작업 상태");
    await loadJobs(); await loadDashboard();
  } catch (error) {
    text("form-error", error.message);
    if (error.definitive) {
      state.pending = null; savePending(); text("job-status", "요청이 거부되었습니다. 문구와 선택을 확인하세요.");
      if (!state.categories.length) await loadCategories();
    } else text("job-status", "요청이 접수됐는지 확인이 필요합니다. 같은 요청 다시 확인 버튼으로 앞서 보낸 요청을 확인하세요.");
  } finally { state.busy = false; controls(); }
}
function media(record, parent) {
  const audioURL = safeURL(record.audio_url), downloadURL = safeURL(record.download_url);
  if (!audioURL && !downloadURL) return;
  const row = element("div", null, "media");
  if (audioURL) {
    const audio = document.createElement("audio"); audio.controls = true; audio.preload = "metadata"; audio.src = audioURL;
    audio.setAttribute("aria-label", `${record.title || "음악"} 재생`);
    audio.addEventListener("play", () => {
      if (playingAudio && playingAudio !== audio) playingAudio.pause();
      playingAudio = audio;
    });
    const message = element("span", "", "note"); message.setAttribute("role", "status");
    audio.addEventListener("error", () => { message.textContent = "재생하지 못했습니다. 목록을 새로고침하거나 다운로드를 이용하세요."; });
    row.append(audio, message);
  }
  if (downloadURL) { const link = element("a", "음원 다운로드"); link.href = downloadURL; link.download = ""; row.append(link); }
  parent.append(row);
}
function pageSlice(kind, records) {
  const sizeKey = `${kind}Size`, pageKey = `${kind}Page`;
  const size = [20, 50, 100].includes(state[sizeKey]) ? state[sizeKey] : 20;
  const pages = Math.max(1, Math.ceil(records.length / size));
  const page = Math.max(1, Math.min(pages, Number.isInteger(state[pageKey]) ? state[pageKey] : 1));
  state[sizeKey] = size; state[pageKey] = page;
  $(`${kind}-size`).value = String(size);
  $(`${kind}-previous`).disabled = page === 1;
  $(`${kind}-next`).disabled = page === pages;
  const start = (page - 1) * size;
  text(`${kind}-range`, `${page} / ${pages}페이지 · ${records.length ? `${start + 1}–${Math.min(start + size, records.length)} / 총 ${records.length}개` : "0개"}`);
  return records.slice(start, start + size);
}
function renderJobs() { renderRecords("job-list", pageSlice("jobs", state.jobs || []), true); }
function resetLibraryPage() { state.libraryPage = 1; renderLibrary(); }
function bindPagination() {
  ["library", "jobs"].forEach(kind => {
    const render = kind === "library" ? renderLibrary : renderJobs;
    $(`${kind}-size`).addEventListener("change", () => { state[`${kind}Size`] = Number($(`${kind}-size`).value); state[`${kind}Page`] = 1; render(); });
    [["previous", -1], ["next", 1]].forEach(([direction, offset]) => {
      $(`${kind}-${direction}`).addEventListener("click", () => { state[`${kind}Page`] = (state[`${kind}Page`] || 1) + offset; render(); });
    });
  });
}
const favoriteSaves = new Set();
const favoriteChanges = new Map();
let favoriteRevision = 0;
function updateFavoriteButton(button, record) {
  button.textContent = record.favorite ? "★" : "☆";
  button.setAttribute("aria-pressed", String(record.favorite === true));
  button.setAttribute("aria-label", `${record.title || "제목 없는 음악"} 즐겨찾기 ${record.favorite ? "해제" : "등록"}`);
  button.title = record.favorite ? "즐겨찾기 해제" : "즐겨찾기 등록";
  button.disabled = favoriteSaves.has(record.id);
}
async function toggleFavorite(id, button) {
  const record = state.library.find(item => item.id === id);
  if (!record || button.disabled || favoriteSaves.has(id)) return;
  favoriteSaves.add(id); button.disabled = true;
  try {
    const result = await api(`/api/library/${encodeURIComponent(id)}/favorite`, { favorite: !record.favorite });
    if (result.id !== id || typeof result.favorite !== "boolean") throw new Error("즐겨찾기 저장 결과를 확인하지 못했습니다.");
    favoriteChanges.set(id, { revision: ++favoriteRevision, favorite: result.favorite });
    // Merge into the latest list if a refresh completed during the save.
    state.library.forEach(item => { if (item.id === id) item.favorite = result.favorite; });
    renderLibrary();
    text("favorite-message", result.favorite ? "즐겨찾기에 추가했습니다." : "즐겨찾기를 해제했습니다.");
  } catch (error) { text("favorite-message", `즐겨찾기를 저장하지 못했습니다. ${error.message}`); }
  finally { favoriteSaves.delete(id); button.disabled = false; renderLibrary(); }
}
function renderRecords(target, records, jobs = false, startIndex = 0) {
  const container = $(target);
  // Keep existing audio elements alive across status polling and search refreshes.
  const old = new Map(Array.from(container.children).map((node) => [node.dataset.id, node]));
  const nodes = records.map((record, index) => {
    const orderLabel = String(startIndex + index + 1).padStart(2, "0");
    const { favorite, ...content } = record;
    const fingerprint = JSON.stringify(content);
    const existing = old.get(String(record.id));
    if (existing && existing.dataset.fingerprint === fingerprint) {
      const timer = existing.querySelector("[data-elapsed]"); if (timer) timer.textContent = elapsed(record);
      const order = existing.querySelector("[data-order]"); if (order) { order.textContent = orderLabel; order.setAttribute("aria-label", `목록 순서 ${startIndex + index + 1}`); }
      const button = existing.querySelector("button"); if (!jobs && target === "library-list" && button) updateFavoriteButton(button, record);
      return existing;
    }
    const article = element("article", null, "record"); article.dataset.id = String(record.id); article.dataset.fingerprint = fingerprint;
    const heading = element("div", null, "record-heading");
    if (target === "library-list") {
      const order = element("span", orderLabel, "record-order"); order.dataset.order = "";
      order.setAttribute("aria-label", `목록 순서 ${startIndex + index + 1}`); heading.append(order);
    }
    heading.append(element("h3", record.title || "제목 없는 음악"));
    heading.append(element("span", jobs ? (labels[record.status] || "상태 확인 필요") : sourceLabel(record.source), "badge"));
    if (!jobs && target === "library-list") {
      const button = element("button", null, "favorite-button"); button.type = "button";
      updateFavoriteButton(button, record); button.addEventListener("click", () => toggleFavorite(record.id, button)); heading.append(button);
    }
    article.append(heading);
    const meta = element("p", [record.category_id || "카테고리 정보 없음", record.variant_id || "변형 정보 없음", duration(record.duration_seconds), dateLabel(record.created_at)].filter(Boolean).join(" · "), "note");
    const timer = element("span", elapsed(record)); timer.dataset.elapsed = ""; meta.append(timer); article.append(meta);
    if (jobs && ["failed", "interrupted"].includes(record.status)) article.append(element("p", record.error || "작업이 완료되지 않았습니다.", "note"));
    if (!jobs || record.status === "completed") {
      if (!safeURL(record.audio_url) && !safeURL(record.download_url)) article.append(element("p", "결과 파일을 확인해 주세요", "note"));
      else media(record, article);
    }
    if (record.music_prompt || record.model) {
      const details = element("details");
      details.append(element("summary", record.music_prompt ? "실제 프롬프트 보기" : "음원 정보 보기"));
      if (record.model) details.append(element("p", `모델 · ${record.model}`, "note"));
      if (record.music_prompt) details.append(element("p", record.music_prompt, "prompt-copy"));
      article.append(details);
    }
    return article;
  });
  // Reconcile without detaching unchanged players, so polling does not stop playback.
  nodes.forEach((node, index) => { if (container.children[index] !== node) container.insertBefore(node, container.children[index] || null); });
  const keep = new Set(nodes); Array.from(container.children).forEach((node) => {
    if (!keep.has(node)) {
      const audio = node.querySelector("audio");
      if (audio) { if (!audio.paused) audio.pause(); if (playingAudio === audio) playingAudio = null; }
      node.remove();
    }
  });
}
function jobSummary(jobs) {
  const counts = new Map();
  jobs.forEach((job) => { const label = labels[job.status] || "상태 확인 필요"; counts.set(label, (counts.get(label) || 0) + 1); });
  return [...counts].sort(([a], [b]) => a.localeCompare(b, "ko")).map(([label, count]) => `${label} ${count}개`).join(" · ");
}
async function loadJobs() {
  if (state.jobsBusy) return;
  state.jobsBusy = true; $("job-list").setAttribute("aria-busy", "true");
  try {
    const jobs = items(await api("/api/jobs")); state.jobs = jobs; renderJobs();
    const activeCount = jobs.filter(active).length;
    if ($("sidebar-generation")) text("sidebar-generation", activeCount ? `생성 진행 ${activeCount}개` : "진행 작업 없음");
    const newlyCompleted = jobs.some((job) => job.status === "completed" && ["queued", "generating_music"].includes(state.jobStatuses?.get(job.id)));
    state.jobStatuses = new Map(jobs.map((job) => [job.id, job.status]));
    if (newlyCompleted) loadLibrary();
    text("jobs-message", jobs.length ? `작업 ${jobs.length}개 · ${jobSummary(jobs)}` : "아직 생성한 작업이 없습니다.");
    text("jobs-updated", `마지막 조회 ${new Date().toLocaleTimeString("ko-KR")}`);
    if (state.pending?.jobId) {
      const current = jobs.find((job) => job.id === state.pending.jobId);
      if (current) {
        text("job-status", labels[current.status] || "상태 확인 필요");
        if (["completed", "failed", "interrupted"].includes(current.status)) {
          state.pending = null; state.preview = null; savePending(); $("new-draft").hidden = false;
          if (current.status === "completed" && !newlyCompleted) loadLibrary();
          text("form-error", current.status === "completed" ? "" : current.error || "작업이 완료되지 않았습니다.");
        }
      } else text("job-status", "접수한 작업이 목록에 없습니다. 새로 만들지 말고 작업 새로고침을 눌러 다시 확인하세요.");
    }
  } catch (error) {
    text("jobs-message", error.message);
    if ($("sidebar-generation")) text("sidebar-generation", "확인 불가");
  }
  finally { state.jobsBusy = false; $("job-list").setAttribute("aria-busy", "false"); controls(); }
}
async function loadDashboard() {
  $("dashboard").setAttribute("aria-busy", "true");
  try {
    const data = await api("/api/dashboard");
    text("track-count", data.track_count ?? "확인 필요"); text("total-duration", duration(data.total_duration_seconds)); text("active-count", Array.isArray(data.active_jobs) ? data.active_jobs.length : "확인 필요");
    const jobs = [...(data.active_jobs || []), ...(data.recent_errors || [])];
    renderRecords("dashboard-jobs", [...new Map(jobs.map((job) => [job.id, job])).values()], true);
    text("dashboard-message", jobs.length ? jobSummary([...new Map(jobs.map((job) => [job.id, job])).values()]) : "진행 작업과 최근 오류가 없습니다.");
    text("dashboard-updated", `마지막 조회 ${new Date().toLocaleTimeString("ko-KR")}`);
  } catch (error) { text("dashboard-message", error.message); }
  finally { $("dashboard").setAttribute("aria-busy", "false"); }
}
function sourceLabel(value) { return ({ web: "웹 생성", web_job: "웹 생성", "web-jobs": "웹 생성", automation: "기존 자동화", track: "기존 트랙", archived: "보관된 트랙" })[value] || value || "출처 정보 없음"; }
let libraryCategory = null;
function libraryCategoryKey(item) { return typeof item.category_id === "string" ? item.category_id.trim() : ""; }
function libraryCategoryLabel(key) {
  return ({ study: "Study", lofi: "Lo-fi", phonk: "Phonk", cafe: "Cafe", fitness: "Fitness", "fitness-metal": "Fitness Metal", "fitness-rock": "Fitness Rock", jazz: "Jazz", sleep: "Sleep", "japan-city-pop": "Japan City Pop" })[key] || key || "미분류";
}
function selectLibraryCategory(key) { if (libraryCategory !== key) state.libraryPage = 1; libraryCategory = key; renderLibrary(); }
function renderLibrary() {
  const search = $("library-search").value.trim().toLocaleLowerCase(); const source = $("source-filter").value;
  const matches = state.library.filter((item) => (!$("favorites-only").checked || item.favorite === true) && (source === "all" || item.source === source) && [item.title, item.category_id, item.variant_id].filter(Boolean).join(" ").toLocaleLowerCase().includes(search));
  const keys = [...new Set(state.library.map(libraryCategoryKey))].sort((a,b) => a === "" ? 1 : b === "" ? -1 : a.localeCompare(b));
  if (libraryCategory !== null && !keys.includes(libraryCategory)) { libraryCategory = null; state.libraryPage = 1; }
  const tabs = $("library-categories");
  if (tabs) {
    const choices = [null, ...keys];
    const existing = new Map(Array.from(tabs.children).map(node => [node.dataset.category, node]));
    const buttons = choices.map(key => {
      const identity = JSON.stringify(key);
      const button = existing.get(identity) || element("button");
      if (!existing.has(identity)) { button.type = "button"; button.dataset.category = identity; button.addEventListener("click", () => selectLibraryCategory(key)); }
      button.textContent = `${key === null ? "전체" : libraryCategoryLabel(key)} (${key === null ? matches.length : matches.filter(item => libraryCategoryKey(item) === key).length})`;
      button.setAttribute("aria-pressed", String(key === libraryCategory));
      return button;
    });
    buttons.forEach((button,index) => { if (tabs.children[index] !== button) tabs.insertBefore(button,tabs.children[index] || null); });
    Array.from(tabs.children).forEach(button => { if (!buttons.includes(button)) button.remove(); });
  }
  const filtered = matches.filter(item => libraryCategory === null || libraryCategoryKey(item) === libraryCategory);
  if (libraryCategory === null) filtered.sort((a,b) => keys.indexOf(libraryCategoryKey(a)) - keys.indexOf(libraryCategoryKey(b)));
  const container = $("library-list");
  const headers = new Map(Array.from(container.children).filter(node => node.dataset.categoryHeading !== undefined).map(node => [node.dataset.categoryHeading,node]));
  headers.forEach(node => node.remove());
  const visible = pageSlice("library", filtered);
  renderRecords("library-list", visible, false, (state.libraryPage - 1) * state.librarySize);
  if (libraryCategory === null) {
    const articles = Array.from(container.children);
    keys.forEach(key => {
      const index = visible.findIndex(item => libraryCategoryKey(item) === key);
      if (index < 0) return;
      const heading = headers.get(key) || element("h3", null, "library-category-heading");
      heading.dataset.categoryHeading = key;
      heading.textContent = `${libraryCategoryLabel(key)} · 전체 ${filtered.filter(item => libraryCategoryKey(item) === key).length}곡`;
      container.insertBefore(heading, articles[index]);
    });
  }
  const count = `전체 ${state.library.length}곡 · 조건에 맞는 ${filtered.length}곡${state.libraryWarning || ""}`;
  if (state.libraryError) {
    text("library-message", `${state.libraryError} ${state.libraryLoaded ? `마지막으로 불러온 목록입니다. ${count}` : "목록을 불러오지 못했습니다."} 목록 새로고침으로 다시 확인하세요.`);
  } else {
    text("library-message", `${count}${!state.library.length ? " · 재생 가능한 음악이 없습니다." : !filtered.length ? " · 조건에 맞는 음악이 없습니다." : ""}`);
  }
}
async function loadLibrary() {
  if (state.libraryBusy) return;
  state.libraryBusy = true;
  $("library-list").setAttribute("aria-busy", "true");
  const revision = favoriteRevision;
  try {
    const data = await api("/api/library"); state.library = items(data); state.libraryWarning = data.unreadable_count ? ` · ${data.unreadable_count}개 항목을 읽지 못했습니다` : "";
    // A read started before a successful save must not undo its visible result.
    state.library.forEach(item => { const change = favoriteChanges.get(item.id); if (change && change.revision > revision) item.favorite = change.favorite; });
    const selected = $("source-filter").value;
    $("source-filter").replaceChildren(new Option("모든 출처", "all"));
    [...new Set(state.library.map((item) => item.source).filter(Boolean))].forEach((source) => $("source-filter").add(new Option(sourceLabel(source), source)));
    if (Array.from($("source-filter").options).some((option) => option.value === selected)) $("source-filter").value = selected;
    if ($("source-filter").value !== selected) state.libraryPage = 1;
    state.libraryError = null; state.libraryLoaded = true;
    renderLibrary();
  } catch (error) { state.libraryError = error.message; renderLibrary(); }
  finally { state.libraryBusy = false; $("library-list").setAttribute("aria-busy", "false"); }
}
function schedulerControls() {
  const value = state.scheduler;
  const supported = value?.supported === true && value?.installed === true;
  const recovery = supported && typeof value.registered === "boolean" && value.state === "partial_failure";
  const persistDisable = supported && value.registered === false && value.state === "disabled" && value.enabled === false;
  const ready = !state.schedulerBusy && supported && typeof value.enabled === "boolean" && ["enabled", "disabled"].includes(value.state);
  $("scheduler-enable").disabled = state.schedulerBusy || (!recovery && (!ready || value.enabled));
  $("scheduler-disable").disabled = state.schedulerBusy || (!recovery && !persistDisable && (!ready || !value.enabled));
  text("scheduler-enable", recovery ? "켜기 재시도" : "자동화 켜기");
  text("scheduler-disable", recovery ? "끄기 재시도" : "자동화 끄기");
  $("refresh-scheduler").disabled = state.schedulerBusy;
}
function renderScheduler(data) {
  state.scheduler = data;
  const yesNo = (value) => value === true ? "예" : value === false ? "아니오" : "확인 불가";
  const status = { enabled: "켜짐", disabled: "꺼짐", unknown: "확인 불가", not_installed: "미설치", unsupported: "미지원", partial_failure: "일부 실패 · 복구 확인 필요" };
  if ($("sidebar-scheduler")) text("sidebar-scheduler", data.state === "partial_failure" ? "확인 불가" : status[data.state] || "확인 불가");
  if ($("sidebar-scheduler-updated")) text("sidebar-scheduler-updated", `마지막 확인 ${dateLabel(data.observed_at)}`);
  const rows = [["예약 상태", status[data.state] || "확인 불가"], ["설치됨", yesNo(data.installed)], ["등록됨", yesNo(data.registered)], ["실행 중", yesNo(data.running)], ["일정", data.schedule ? `${String(data.schedule.hour).padStart(2, "0")}:${String(data.schedule.minute).padStart(2, "0")} · 운영체제 예약 시간` : "일정 정보 없음"], ["카테고리", data.category_id || "정보 없음"], ["확인 시각", dateLabel(data.observed_at)]];
  $("scheduler-details").replaceChildren(...rows.flatMap(([label, value]) => [element("dt", label), element("dd", value)]));
  text("scheduler-message", data.error || "방금 확인한 상태입니다. 상태를 바꾸기 전에는 한 번 더 묻습니다."); schedulerControls();
}
function schedulerFailure(error) {
  const data = error.data;
  if (data && ["unknown", "partial_failure", "unsupported", "not_installed"].includes(data.state)) {
    renderScheduler(data);
    const recovery = data.state === "partial_failure" && data.supported === true && data.installed === true && typeof data.registered === "boolean";
    text("scheduler-message", `${error.message} 지금 예약 상태를 확인할 수 없습니다.${recovery ? " 켜기 또는 끄기 버튼을 눌러 원하는 상태로 다시 시도하세요." : ""}`);
  } else {
    renderScheduler({ state: "unknown", supported: null, installed: null, registered: null, running: null, enabled: null, schedule: null, category_id: null, observed_at: null });
    text("scheduler-message", `${error.message} 지금 상태를 확인할 수 없어 이전 상태도 표시하지 않습니다.`);
  }
}
async function loadScheduler() {
  if (state.schedulerBusy) return;
  state.schedulerBusy = true; schedulerControls();
  try { renderScheduler(await api("/api/scheduler")); }
  catch (error) { schedulerFailure(error); }
  finally { state.schedulerBusy = false; schedulerControls(); }
}
async function setScheduler(enabled) {
  if (state.schedulerBusy || (enabled ? $("scheduler-enable") : $("scheduler-disable")).disabled) return;
  if (!window.confirm(enabled ? "자동화를 켤까요? 현재 기본 설정은 음악만 쌓고 배치 업로드는 꺼져 있습니다. 설정에서 배치 업로드를 허용한 경우에만 이미지 생성·MP4 취합·YouTube 업로드·success 자동 이동을 실행합니다." : "다음 예약 실행부터 끌까요? 이미 실행 중인 작업은 강제로 멈추지 않습니다.")) return;
  state.schedulerBusy = true; schedulerControls(); text("scheduler-message", "변경 후 실제 상태를 확인하고 있습니다.");
  try {
    await api("/api/scheduler", { enabled });
    const observed = await api("/api/scheduler"); renderScheduler(observed);
    text("scheduler-message", observed.enabled === enabled && observed.state === (enabled ? "enabled" : "disabled") ? "원하는 상태로 바뀐 것을 확인했습니다." : "요청한 상태와 실제 상태가 다릅니다. 다시 확인하세요.");
  } catch (error) { schedulerFailure(error); text("scheduler-message", `${$("scheduler-message").textContent} 상태가 바뀌었는지 확인하지 못했습니다. 다시 확인하세요.`); }
  finally { state.schedulerBusy = false; schedulerControls(); }
}
document.querySelector(".skip-link").addEventListener("click", skipToContent);
$("category").addEventListener("change", () => {
  if (!confirmDiscard()) { $("category").value = selectedCategory; return; }
  selectedCategory = $("category").value; fillVariants(); invalidatePreview();
});
$("variant").addEventListener("change", () => {
  if (!confirmDiscard()) { $("variant").value = selectedVariant; return; }
  selectedVariant = $("variant").value; invalidatePreview();
});
$("music-prompt").addEventListener("input", controls);
$("preview").addEventListener("click", preview);
$("create-job").addEventListener("click", createJob);
$("retry-submit").addEventListener("click", submitPending);
$("new-draft").addEventListener("click", async () => { invalidatePreview(); $("new-draft").hidden = true; text("job-status", "새 미리보기를 확인하세요. 이전에 수정한 문구는 이어 쓰지 않습니다."); if (!state.categories.length) await loadCategories(); $("category").focus(); });
$("reload-categories").addEventListener("click", loadCategories);
$("refresh-jobs").addEventListener("click", loadJobs);
$("refresh-dashboard").addEventListener("click", loadDashboard);
$("refresh-library").addEventListener("click", loadLibrary);
$("refresh-scheduler").addEventListener("click", loadScheduler);
$("scheduler-enable").addEventListener("click", () => setScheduler(true));
$("scheduler-disable").addEventListener("click", () => setScheduler(false));
$("library-search").addEventListener("input", resetLibraryPage);
$("source-filter").addEventListener("change", resetLibraryPage);
$("favorites-only").addEventListener("change", resetLibraryPage);
bindPagination();
window.addEventListener("hashchange", () => { route(); $("content").focus(); });
try {
  const pending = JSON.parse(sessionStorage.getItem("automusic.pending"));
  if (pending?.body?.request_id && pending.body.preview_id && typeof pending.body.music_prompt === "string") {
    state.pending = pending; $("music-prompt").value = pending.body.music_prompt;
    text("job-status", pending.jobId ? "접수한 작업이 어디까지 진행됐는지 확인하고 있습니다." : "요청이 접수됐는지 확인이 필요합니다. 같은 요청 다시 확인을 눌러주세요.");
  }
} catch { /* A malformed saved request is ignored; no request is replayed automatically. */ }
route(); controls();
if (!state.pending) loadCategories();
loadJobs(); loadDashboard(); loadLibrary(); loadScheduler();
window.setInterval(() => { if (!document.hidden) loadJobs(); }, 4000);
window.setInterval(() => { if (!document.hidden && !$("dashboard").hidden) loadDashboard(); }, 15000);
