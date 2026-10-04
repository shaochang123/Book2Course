const $ = (selector) => document.querySelector(selector);
const form = $("#upload-form");
const fileInput = $("#pdf-file");
const dropzone = $("#dropzone");
const representationNames = {geometry: "可计算几何", process: "过程图", relationship: "关系图", comparison: "对比图", source_figure: "原文图示讲解"};
const linkedJobId = new URLSearchParams(window.location.search).get("job") || "";
let currentJobId = /^[0-9a-f]{32}$/.test(linkedJobId) ? linkedJobId : localStorage.getItem("zhijiang-job-id");
let pollTimer = null;
let config = null;
let shownSettingsJobId = null;

async function getJSON(url, options = {}) {
  const response = await fetch(url, options);
  let data = {};
  try { data = await response.json(); } catch (_) { /* Empty responses are valid for DELETE. */ }
  if (!response.ok) {
    const message = typeof data.detail === "string" ? data.detail : `请求失败（${response.status}）`;
    throw new Error(message);
  }
  return data;
}

function selected(name) { return form.querySelector(`input[name="${name}"]:checked`)?.value; }

function isLocalURL(value) {
  try { return ["localhost", "127.0.0.1", "[::1]"].includes(new URL(value).hostname); }
  catch (_) { return false; }
}

function updateConsent() {
  const ai = selected("mode") === "ai";
  const aiVoice = selected("voice_mode") === "ai";
  $("#ai-settings").hidden = !ai;
  $("#tts-settings").hidden = !aiVoice;
  const modelURL = $("#llm-base-url").value || config?.llm_base_url || "";
  const ttsURL = $("#tts-base-url").value || config?.tts_base_url || "";
  const localVoice = isLocalURL(ttsURL);
  const remote = (ai && !isLocalURL(modelURL)) || (aiVoice && !localVoice);
  $("#remote-consent-row").hidden = !remote;
  $("#remote-consent").required = remote;
  if (!remote) $("#remote-consent").checked = false;
  $("#llm-api-key").required = ai && $("#llm-provider").value === "openai" && !config?.llm_ready;
  $("#api-key-hint").textContent = $("#llm-provider").value === "ollama" ? "本机 Ollama 无需填写" :
    (config?.llm_ready ? "服务器已有默认密钥；更换接口时请填写" : "兼容接口需要填写");
  for (const name of ["tts_base_url", "tts_model", "tts_voice"]) {
    form.elements[name].required = aiVoice;
  }
  const usesDefaultVoice = ttsURL === config?.tts_base_url &&
    $("#tts-model").value === config?.tts_model && $("#tts-voice").value === config?.tts_voice;
  $("#tts-api-key").required = aiVoice && !localVoice && !(usesDefaultVoice && config?.ai_tts_ready);
  $("#tts-key-hint").textContent = localVoice ? "本机服务无需填写" : "外部服务需要填写；默认服务可使用服务器密钥";
}

function setFile(file) {
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;
  $("#file-label").textContent = file.name;
}

dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); fileInput.click(); }
});
dropzone.addEventListener("dragover", (event) => { event.preventDefault(); dropzone.classList.add("dragover"); });
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (event) => {
  event.preventDefault(); dropzone.classList.remove("dragover");
  if (event.dataTransfer.files.length) setFile(event.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => { if (fileInput.files.length) $("#file-label").textContent = fileInput.files[0].name; });
form.querySelectorAll('input[type="radio"]').forEach((input) => input.addEventListener("change", updateConsent));
$("#llm-provider").addEventListener("change", updateConsent);
$("#animation-mode").addEventListener("change", () => {
  if (["math","visual"].includes($("#animation-mode").value)) form.querySelector('input[name="mode"][value="ai"]').checked = true;
  updateConsent();
});
$("#llm-base-url").addEventListener("input", updateConsent);
for (const name of ["tts_base_url", "tts_model", "tts_voice"]) {
  form.elements[name].addEventListener("input", updateConsent);
}

function showJob(job) {
  if (shownSettingsJobId !== job.id) {
    shownSettingsJobId = job.id;
    const modeChoice = form.querySelector(`input[name="mode"][value="${job.mode}"]`);
    if (modeChoice) modeChoice.checked = true;
    const voiceChoice = form.querySelector(`input[name="voice_mode"][value="${job.voice_mode}"]`);
    if (voiceChoice) voiceChoice.checked = true;
    if (job.mode === "ai" && job.model_settings) {
      $("#llm-provider").value = job.model_settings.provider || "openai";
      $("#llm-base-url").value = job.model_settings.base_url || "";
      $("#llm-model").value = job.model_settings.model || "";
      $("#custom-prompt").value = job.model_settings.prompt || "";
      $("#animation-mode").value = job.model_settings.animation_mode || "auto";
    }
    if (job.voice_mode === "ai" && job.voice_settings) {
      $("#tts-base-url").value = job.voice_settings.base_url || "";
      $("#tts-model").value = job.voice_settings.model || "";
      $("#tts-voice").value = job.voice_settings.voice || "";
    }
    updateConsent();
    if (!$("#remote-consent-row").hidden) $("#remote-consent").checked = job.remote_consent;
  }
  $("#job-section").hidden = false;
  $("#job-filename").textContent = job.filename || "";
  const badge = $("#job-badge");
  const states = { queued: "排队中", running: "生成中", completed: "已完成", failed: "失败" };
  badge.textContent = states[job.status] || job.status;
  badge.className = `status-badge ${job.status}`;
  const stages = { queued: "等待处理", completed: "生成完成", failed: "生成失败", interrupted: "服务中断" };
  $("#job-stage").textContent = stages[job.stage] || job.stage || "等待处理";
  $("#job-progress").style.width = `${job.progress || 0}%`;
  $("#job-message").textContent = job.error || (job.status === "completed" ?
    (job.has_presentation ? "视频、PPT 课件与逐段讲稿已生成。" : "视频与逐段讲稿已生成；旧任务可重新上传 PDF 生成 PPT。") :
    "当前任务会在本机逐步处理。请保持页面和服务运行。 ");
  $("#presentation-export").hidden = !(job.status === "completed" && job.has_presentation);
  $("#retry-button").hidden = job.status !== "failed";
  $("#delete-button").hidden = !["completed", "failed"].includes(job.status);
}

function addSegment(segment, index) {
  const details = document.createElement("details");
  details.className = "segment";
  if (index === 0) details.open = true;
  const summary = document.createElement("summary");
  const title = document.createElement("strong");
  title.textContent = `${String(index + 1).padStart(2, "0")} · ${segment.title}`;
  const page = document.createElement("span");
  page.textContent = `PDF 第 ${segment.evidence.page} 页${segment.evidence.ocr ? " · OCR" : ""} ↗`;
  summary.append(title, page);
  const body = document.createElement("div");
  body.className = "segment-body";
  const narration = document.createElement("p");
  narration.textContent = segment.narration;
  const quote = document.createElement("div");
  quote.className = "source-quote";
  quote.textContent = `原文摘录：${segment.evidence.quote}`;
  const scene = segment.math_scene || segment.visual_scene;
  if (!scene) body.append(narration);
  if (scene) {
    if (scene.diagram) {
      const strategy = document.createElement("p");
      strategy.textContent = `教学表达：${representationNames[scene.diagram.representation] || scene.diagram.representation}。${scene.diagram.rationale}`;
      body.append(strategy);
    }
    const steps = document.createElement("ol");
    scene.beats.forEach((beat) => {
      const item = document.createElement("li");
      item.textContent = beat.narration;
      steps.append(item);
    });
    body.append(steps);
  }
  body.append(quote);
  details.append(summary, body);
  $("#segments").append(details);
}

async function showLesson(jobId) {
  const lesson = await getJSON(`/api/jobs/${jobId}/lesson`);
  $("#lesson-result").hidden = false;
  $("#lesson-title").textContent = lesson.title;
  $("#lesson-objective").textContent = lesson.objective;
  $("#lesson-notice").textContent = lesson.notice;
  $("#segment-count").textContent = `${lesson.segments.length} 个讲解片段`;
  $("#voice-note").textContent = lesson.voice_mode === "ai" ? "本视频使用所配置的 AI 语音服务。" : "本视频使用 Windows 系统语音；此配音不是 AI 语音。";
  $("#segments").replaceChildren();
  lesson.segments.forEach(addSegment);
  const videoURL = `/api/jobs/${jobId}/video`;
  $("#lesson-video").src = videoURL;
  $("#download-video").href = videoURL;
  $("#download-presentation").href = `/api/jobs/${jobId}/presentation`;
  const report = lesson.animation_report || {};
  $("#math-report").hidden = !report.renderer;
  $("#math-report").textContent = report.scene_count ? (report.scene_type === "general" ?
    `${report.scene_count} 个通用教学场景 · ${report.renderer} · 含同步配音。表达类型：${[...new Set(report.representations || ["geometry"])].map(name => representationNames[name] || name).join("、")}。来源摘录、关系引用或几何计算按类型检查；教学含义和专业事实需复核。` :
    `${report.scene_count} 个数学推演场景 · ${report.renderer} · 含同步配音。矩阵、向量与几何计算已核验；讲解质量和引用含义仍需人工核对。`) : report.reason || "基础图示";
  $("#download-math-scenes").hidden = !report.scene_count;
  $("#download-math-scenes").href = `/api/jobs/${jobId}/scenes`;
}

async function refreshJob() {
  if (!currentJobId) return;
  try {
    const job = await getJSON(`/api/jobs/${currentJobId}`);
    showJob(job);
    if (job.status === "completed") {
      clearInterval(pollTimer); pollTimer = null;
      await showLesson(currentJobId);
    } else if (job.status === "failed") {
      clearInterval(pollTimer); pollTimer = null;
      $("#lesson-result").hidden = true;
    }
  } catch (error) {
    clearInterval(pollTimer); pollTimer = null;
    if (error.message.includes("任务不存在")) {
      currentJobId = null;
      localStorage.removeItem("zhijiang-job-id");
    }
    $("#job-section").hidden = false;
    $("#job-stage").textContent = error.message;
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  refreshJob();
  pollTimer = setInterval(refreshJob, 1400);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const button = $("#submit-button");
  button.disabled = true;
  button.textContent = "正在提交…";
  try {
    const body = new FormData();
    body.append("file", fileInput.files[0]);
    body.append("mode", selected("mode"));
    body.append("voice_mode", selected("voice_mode"));
    body.append("animation_mode", $("#animation-mode").value);
    body.append("rights_confirmed", String($("#rights-confirmed").checked));
    body.append("remote_consent", String($("#remote-consent").checked));
    if (selected("mode") === "ai") {
      for (const name of ["llm_provider", "llm_base_url", "llm_model", "llm_api_key", "custom_prompt"]) {
        body.append(name, form.elements[name].value);
      }
    }
    if (selected("voice_mode") === "ai") {
      for (const name of ["tts_base_url", "tts_model", "tts_voice", "tts_api_key"]) {
        body.append(name, form.elements[name].value);
      }
    }
    const job = await getJSON("/api/jobs", { method: "POST", body });
    $("#llm-api-key").value = "";
    $("#tts-api-key").value = "";
    currentJobId = job.id;
    localStorage.setItem("zhijiang-job-id", job.id);
    $("#lesson-result").hidden = true;
    showJob(job);
    $("#job-section").scrollIntoView({ behavior: "smooth", block: "start" });
    startPolling();
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = '生成一节课 <span aria-hidden="true">↗</span>';
  }
});

$("#delete-button").addEventListener("click", async () => {
  if (!currentJobId || !confirm("确定删除此任务的本地 PDF、课程、视频和 PPT 吗？")) return;
  try {
    await getJSON(`/api/jobs/${currentJobId}`, { method: "DELETE" });
    currentJobId = null;
    localStorage.removeItem("zhijiang-job-id");
    $("#job-section").hidden = true;
    $("#lesson-result").hidden = true;
    $("#lesson-video").removeAttribute("src");
    $("#lesson-video").load();
  } catch (error) { alert(error.message); }
});

$("#retry-button").addEventListener("click", async () => {
  if (!currentJobId) return;
  const button = $("#retry-button");
  button.disabled = true;
  try {
    const body = new FormData();
    body.append("mode", selected("mode"));
    body.append("voice_mode", selected("voice_mode"));
    body.append("animation_mode", $("#animation-mode").value);
    body.append("remote_consent", String($("#remote-consent").checked));
    body.append("replace_settings", "true");
    if (selected("mode") === "ai") {
      for (const name of ["llm_provider", "llm_base_url", "llm_model", "llm_api_key", "custom_prompt"]) {
        body.append(name, form.elements[name].value);
      }
    }
    if (selected("voice_mode") === "ai") {
      for (const name of ["tts_base_url", "tts_model", "tts_voice", "tts_api_key"]) {
        body.append(name, form.elements[name].value);
      }
    }
    const job = await getJSON(`/api/jobs/${currentJobId}/retry`, { method: "POST", body });
    $("#llm-api-key").value = "";
    $("#tts-api-key").value = "";
    $("#lesson-result").hidden = true;
    showJob(job);
    startPolling();
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
  }
});

(async function initialize() {
  try {
    config = await getJSON("/api/config");
    $("#math-ready-label").textContent = config.math_animation?.ready ?
      "教学动画环境就绪：通用场景支持各学科；二维线性变换提供专用推演。" :
      `数学动画环境未就绪：${config.math_animation?.reason || "请安装 math-animation 依赖"}。基础图示仍可使用。`;
    $("#pdf-limits").textContent = `文字版和扫描版 PDF · 最多 ${Math.round(config.max_pdf_bytes / 1024 / 1024)} MB · 无页数上限`;
    $("#llm-provider").value = config.llm_provider === "ollama" ? "ollama" : "openai";
    $("#llm-base-url").value = config.llm_base_url || "";
    $("#llm-model").value = config.llm_model || "";
    $("#tts-base-url").value = config.tts_base_url || "";
    $("#tts-model").value = config.tts_model || "";
    $("#tts-voice").value = config.tts_voice || "";
    $("#ai-ready-label").textContent = config.llm_ready ?
      `默认：${config.llm_provider} · ${config.llm_model}；可在下方修改` : "在下方填写本次使用的模型 API";
    $("#tts-ready-label").textContent = !config.ai_tts_ready ? "可在下方填写本次使用的语音 API" :
      (config.tts_is_local ? "默认连接本机语音模型；可在下方修改" : "默认连接外部语音服务；可在下方修改");
    updateConsent();
    if (currentJobId) startPolling();
  } catch (error) {
    $("#ai-ready-label").textContent = "配置读取失败";
    $("#tts-ready-label").textContent = "配置读取失败";
  }
})();
