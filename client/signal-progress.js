/** Local phase presentation only. No network, workload estimation or retry. */
export const SIGNAL_PHASES = Object.freeze({
  detection: { text: "определение области лиц", progress: 0 },
  crops: { text: "обрезка лиц для поиска фоток", progress: 25 },
  search: { text: "поиск ваших фотографий", progress: 45 },
  photos: { text: "получение ваших фотографий", progress: 80 },
});

export function createSignalProgress({ document = globalThis.document, parent = document.body } = {}) {
  const element = document.createElement("section");
  element.className = "signal-progress";
  element.hidden = true;
  element.setAttribute("aria-label", "Подготовка ваших фотографий");
  const paths = Array.from({ length: 7 }, (_, i) => {
    const y = 70 + i * 460 / 6;
    const inner = 210 + i * 30;
    // Every bend has horizontal tangents at both ends. The geometry is static.
    const d = `M0 ${y} H160 C270 ${y} 280 ${inner} 380 ${inner} H620 C720 ${inner} 730 ${y} 840 ${y} H1000`;
    return `<path class="signal-guide" d="${d}"/><path class="signal-packet" d="${d}" pathLength="100" style="animation-delay:-${i * .57 / .4}s"/>`
      + ([0, 6].includes(i) ? `<path class="signal-fill" d="${d}" pathLength="100"/>` : "");
  }).join("");
  element.innerHTML = `<svg class="signal-routes" viewBox="0 0 1000 600" preserveAspectRatio="none" fill="none" aria-hidden="true">${paths}</svg><p class="signal-caption" role="status" aria-live="polite" aria-atomic="true"></p>`;
  parent.append(element);
  const caption = element.querySelector(".signal-caption");
  const fills = element.querySelectorAll(".signal-fill");
  let captureId = null, attemptId = null, hiding = null;

  function hide() {
    if (hiding !== null) clearTimeout(hiding);
    hiding = null; element.hidden = true;
    element.classList.remove("is-revealing");
    document.body.classList.remove("signal-active");
    captureId = null; attemptId = null;
  }
  function setProgress(value) {
    fills.forEach(path => { path.style.strokeDashoffset = String(100 - value); });
    element.dataset.progress = String(value);
  }
  return {
    element,
    begin(id) {
      hide();
      captureId = String(id);
      element.dataset.phase = "detection";
      caption.textContent = SIGNAL_PHASES.detection.text;
      setProgress(0); element.hidden = false;
      document.body.classList.add("signal-active");
    },
    bind(capture, attempt) {
      if (String(capture) === captureId) attemptId = String(attempt);
    },
    phase(id, phase) {
      if (captureId === null || (String(id) !== captureId && String(id) !== attemptId)) return;
      if (hiding !== null || !SIGNAL_PHASES[phase]) return;
      const current = Number(element.dataset.progress);
      if (SIGNAL_PHASES[phase].progress < current) return;
      element.dataset.phase = phase;
      caption.textContent = SIGNAL_PHASES[phase].text;
      setProgress(SIGNAL_PHASES[phase].progress);
    },
    reveal(id, card) {
      if (captureId === null || String(id) !== attemptId) return;
      setProgress(100);
      element.classList.add("is-revealing");
      document.body.classList.remove("signal-active");
      // Result and QR are above the retiring flow; nothing covers the QR.
      card.classList.add("has-signal-handoff");
      if (globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches) hide();
      else hiding = setTimeout(hide, 450);
    },
    cancel(id) {
      if (String(id) === captureId || String(id) === attemptId) hide();
    },
    destroy() { hide(); element.remove(); },
  };
}
