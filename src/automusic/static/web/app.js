const presetList = document.querySelector("#preset-list");
const promptField = document.querySelector("#music-prompt");
const createButton = document.querySelector("#create-job");
const formError = document.querySelector("#form-error");
const jobStatus = document.querySelector("#job-status");
const assetLinks = document.querySelector("#asset-links");

let presets = [];
let selectedPresetId = null;

async function loadPresets() {
  try {
    const response = await fetch("/api/presets");
    presets = await response.json();
    renderPresets();
  } catch {
    presetList.replaceChildren();
    const message = document.createElement("p");
    message.textContent = "프리셋을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
    presetList.append(message);
  }
}

function renderPresets() {
  presetList.replaceChildren();
  presets.forEach((preset, index) => {
    const label = document.createElement("label");
    label.className = "preset-option";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "preset";
    input.value = preset.id;
    input.checked = index === 0;
    input.addEventListener("change", () => selectPreset(preset.id));
    const text = document.createElement("span");
    text.textContent = preset.name;
    label.append(input, text);
    presetList.append(label);
  });
  if (presets.length) selectPreset(presets[0].id);
}

function selectPreset(presetId) {
  const preset = presets.find((item) => item.id === presetId);
  if (!preset) return;
  selectedPresetId = preset.id;
  promptField.value = preset.default_prompt;
}

async function createJob() {
  formError.textContent = "";
  assetLinks.replaceChildren();
  if (!selectedPresetId) {
    formError.textContent = "먼저 프리셋을 선택해 주세요.";
    return;
  }
  const musicPrompt = promptField.value.trim();
  if (!musicPrompt) {
    formError.textContent = "프롬프트를 입력해 주세요.";
    return;
  }
  createButton.disabled = true;
  jobStatus.textContent = "작업을 예약하고 있습니다.";
  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preset_id: selectedPresetId, music_prompt: musicPrompt }),
    });
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || "작업을 시작하지 못했습니다.");
    pollJob(job.id);
  } catch (error) {
    formError.textContent = error instanceof Error ? error.message : "작업을 시작하지 못했습니다.";
    jobStatus.textContent = "다시 시도할 수 있습니다.";
    createButton.disabled = false;
  }
}

async function pollJob(jobId) {
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || "작업 상태를 확인하지 못했습니다.");
    jobStatus.textContent = statusMessage(job.status);
    if (job.status === "completed") {
      renderAssetLinks(jobId, job.artifacts);
      createButton.disabled = false;
      return;
    }
    if (job.status === "failed") {
      formError.textContent = job.error || "작업을 완료하지 못했습니다.";
      createButton.disabled = false;
      return;
    }
    window.setTimeout(() => pollJob(jobId), 2000);
  } catch (error) {
    formError.textContent = error instanceof Error ? error.message : "작업 상태를 확인하지 못했습니다.";
    createButton.disabled = false;
  }
}

function statusMessage(status) {
  const messages = {
    queued: "작업을 기다리고 있습니다.",
    generating_music: "음악을 만들고 있습니다.",
    generating_image: "이미지를 만들고 있습니다.",
    rendering_video: "영상을 렌더링하고 있습니다.",
    completed: "작업이 완성되었습니다.",
    failed: "작업을 완료하지 못했습니다.",
  };
  return messages[status] || "작업 상태를 확인하고 있습니다.";
}

function renderAssetLinks(jobId, artifacts) {
  assetLinks.replaceChildren();
  ["audio", "image", "video"].forEach((asset) => {
    if (!artifacts || !artifacts[asset]) return;
    const link = document.createElement("a");
    link.href = `/api/jobs/${encodeURIComponent(jobId)}/downloads/${asset}`;
    link.textContent = `${asset.toUpperCase()} 다운로드`;
    assetLinks.append(link);
  });
}

createButton.addEventListener("click", createJob);
loadPresets();
