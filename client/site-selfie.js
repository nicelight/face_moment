import "./motion-ui.js";

const video = document.querySelector("#selfie-video");
const preview = document.querySelector("#selfie-preview");
const status = document.querySelector("#selfie-status");
const start = document.querySelector("#selfie-start");
const capture = document.querySelector("#selfie-capture");
const retake = document.querySelector("#selfie-retake");
const send = document.querySelector("#selfie-send");
const placeholder = document.querySelector("#selfie-placeholder");
let stream = null, objectUrl = null, generation = 0;

function releaseCamera() {
  stream?.getTracks().forEach(track => track.stop());
  stream = null; video.srcObject = null;
}
function releasePreview() {
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = null; preview.removeAttribute("src"); preview.hidden = true;
}
async function openCamera() {
  const operation = ++generation;
  releaseCamera(); releasePreview();
  start.disabled = true; retake.hidden = true; send.hidden = true;
  placeholder.hidden = false;
  status.textContent = "Разрешите доступ к камере в окне браузера.";
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("camera_unavailable");
    const acquired = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 960 } } });
    if (operation !== generation || document.hidden) { acquired.getTracks().forEach(track => track.stop()); return; }
    stream = acquired;
    video.srcObject = stream; video.hidden = false;
    await video.play();
    if (operation !== generation) return;
    placeholder.hidden = true; start.hidden = true; capture.hidden = false;
    status.textContent = "Посмотрите в камеру. Когда будете готовы, сделайте снимок.";
  } catch (error) {
    if (operation !== generation) return;
    releaseCamera(); video.hidden = true; capture.hidden = true; start.hidden = false;
    status.textContent = error.name === "NotAllowedError"
      ? "Доступ к камере не разрешён. Разрешите его в настройках сайта и повторите попытку."
      : "Не удалось включить камеру. Проверьте её подключение и попробуйте ещё раз.";
  } finally { if (operation === generation) start.disabled = false; }
}
start.addEventListener("click", openCamera);
retake.addEventListener("click", openCamera);
capture.addEventListener("click", async () => {
  if (!video.videoWidth || capture.disabled) return;
  const operation = generation;
  capture.disabled = true;
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
    releaseCamera(); video.hidden = true; preview.hidden = false; capture.hidden = true;
    retake.hidden = false; send.hidden = false;
    status.textContent = "Селфи готово и остаётся в этом браузере. Отправка на поиск станет доступна после запуска сервиса.";
    retake.focus();
  } catch {
    if (operation === generation) status.textContent = "Не удалось сделать снимок. Попробуйте ещё раз.";
  } finally { capture.disabled = false; }
});
function stop() {
  generation += 1; releaseCamera(); releasePreview();
  video.hidden = true; capture.hidden = true; retake.hidden = true; send.hidden = true;
  start.hidden = false; start.disabled = false; placeholder.hidden = false;
  status.textContent = "Камера выключена. Вы можете включить её снова.";
}
window.addEventListener("pagehide", stop);
document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); });
document.querySelectorAll(".fm-nav-links a").forEach(link => link.addEventListener("click", () => link.closest("details").removeAttribute("open")));
