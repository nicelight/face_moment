import "./motion-ui.js";

const video = document.querySelector("#selfie-video");
const preview = document.querySelector("#selfie-preview");
const status = document.querySelector("#selfie-status");
const viewport = document.querySelector("#selfie-viewport");
const retake = document.querySelector("#selfie-retake");
const send = document.querySelector("#selfie-send");
const placeholder = document.querySelector("#selfie-placeholder");
const readyOverlay = document.querySelector("#selfie-ready-overlay");
const searchOverlay = document.querySelector("#selfie-search-overlay");
let stream = null, objectUrl = null, generation = 0, selfieState = "idle", captureInProgress = false;

function releaseCamera() {
  stream?.getTracks().forEach(track => track.stop());
  stream = null; video.srcObject = null;
}
function releasePreview() {
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = null; preview.removeAttribute("src"); preview.hidden = true;
}
function setState(next) {
  selfieState = next;
  viewport.dataset.state = next;
  viewport.disabled = next === "opening" || next === "capturing" || next === "captured";
  viewport.setAttribute("aria-label", next === "ready" ? "Сделать снимок" : "Камера и селфи");
  readyOverlay.toggleAttribute("hidden", next !== "ready");
  searchOverlay.toggleAttribute("hidden", next !== "captured");
}
function waitForVideoFrame() {
  if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.videoWidth && video.videoHeight) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      video.removeEventListener("loadeddata", onReady);
      video.removeEventListener("canplay", onReady);
      video.removeEventListener("resize", onReady);
      video.removeEventListener("error", onError);
    };
    const onReady = () => {
      if (!video.videoWidth || !video.videoHeight) return;
      cleanup(); resolve();
    };
    const onError = () => { cleanup(); reject(new Error("camera_frame_unavailable")); };
    video.addEventListener("loadeddata", onReady);
    video.addEventListener("canplay", onReady);
    video.addEventListener("resize", onReady);
    video.addEventListener("error", onError, { once: true });
    onReady();
  });
}
async function openCamera() {
  const operation = ++generation;
  releaseCamera(); releasePreview();
  setState("opening"); retake.hidden = true; send.hidden = true;
  placeholder.hidden = false;
  status.textContent = "Разрешите доступ к камере в окне браузера.";
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("camera_unavailable");
    const acquired = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 960 } } });
    if (operation !== generation || document.hidden) { acquired.getTracks().forEach(track => track.stop()); return; }
    stream = acquired;
    video.srcObject = stream; video.hidden = false;
    await video.play();
    await waitForVideoFrame();
    if (operation !== generation) return;
    placeholder.hidden = true; setState("ready");
    status.textContent = "Камера готова. Нажмите в любое место изображения, чтобы сделать снимок.";
  } catch (error) {
    if (operation !== generation) return;
    releaseCamera(); video.hidden = true; setState("error");
    status.textContent = error.name === "NotAllowedError"
      ? "Доступ к камере не разрешён. Разрешите его в настройках сайта и нажмите на область селфи, чтобы повторить."
      : "Не удалось включить камеру. Проверьте её подключение и нажмите на область селфи, чтобы повторить.";
  }
}
viewport.addEventListener("click", () => {
  if (selfieState === "idle" || selfieState === "error") void openCamera();
  else if (selfieState === "ready") void captureSelfie();
});
retake.addEventListener("click", openCamera);
async function captureSelfie() {
  if (selfieState !== "ready" || captureInProgress || !video.videoWidth || !video.videoHeight) return;
  const operation = generation;
  captureInProgress = true; setState("capturing");
  try {
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", .9));
    if (operation !== generation) return;
    if (!blob) throw new Error("capture_failed");
    releasePreview(); objectUrl = URL.createObjectURL(blob); preview.src = objectUrl;
    await preview.decode();
    if (operation !== generation) return;
    releaseCamera(); video.hidden = true; preview.hidden = false;
    retake.hidden = false; send.hidden = false; setState("captured");
    status.textContent = "Селфи готово и остаётся в этом браузере. Отправка на поиск станет доступна после запуска сервиса.";
    retake.focus();
  } catch {
    if (operation === generation) {
      setState("ready");
      status.textContent = "Не удалось сделать снимок. Нажмите в любое место изображения и попробуйте ещё раз.";
    }
  } finally { captureInProgress = false; }
}
function stop() {
  generation += 1; releaseCamera(); releasePreview();
  video.hidden = true; retake.hidden = true; send.hidden = true; placeholder.hidden = false;
  setState("idle");
  status.textContent = "Камера выключена. Вы можете включить её снова.";
}
window.addEventListener("pagehide", stop);
document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); });
document.querySelectorAll(".fm-nav-links a").forEach(link => link.addEventListener("click", () => link.closest("details").removeAttribute("open")));
