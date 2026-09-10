import { createPromoCard } from "./promo-display.js";
import { PROMO_LAYOUT_KEY, PROMO_PARTS, readPromoLayout, promoElements, applyPromoLayout } from "./promo-layout.js";

const labels = ["Фото 1", "Фото 2", "Фото 3", "Фото 4", "Текст", "QR-код"];
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

function sampleImage(index) {
  const canvas = document.createElement("canvas");
  canvas.width = index % 2 ? 400 : 600;
  canvas.height = index % 2 ? 600 : 400;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = ["#b18a68", "#667e78", "#9298ac", "#c6a071"][index];
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#fff9eb";
  ctx.textAlign = "center";
  ctx.font = "40px sans-serif";
  ctx.fillText(`Фото ${index + 1}`, canvas.width / 2, canvas.height / 2);
  const image = document.createElement("img");
  image.className = "promo-teaser";
  image.alt = `Образец: фото ${index + 1}`;
  image.src = canvas.toDataURL();
  image.draggable = false;
  return image;
}

export function openPromoLayoutEditor({ onClose = () => {} } = {}) {
  const previousFocus = document.activeElement;
  const root = document.createElement("div");
  root.className = "promo-editor";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "true");
  root.setAttribute("aria-label", "Расположение фотографий");
  const { card } = createPromoCard(document, [0, 1, 2, 3].map(sampleImage), "https://face-momet.ru");
  root.append(card);
  const tools = document.createElement("div");
  tools.className = "promo-editor-tools";
  tools.innerHTML = `<label>Объект <select aria-label="Объект">${labels.map((label, i) => `<option value="${i}">${label}</option>`).join("")}</select></label>
    <label>Размер текста <select aria-label="Размер текста"><option value="0.75">Мелкий</option><option value="1" selected>Средний</option><option value="1.4">Огромный</option></select></label>
    <details><summary>Размер и поворот выбранного объекта</summary>
      <label>Ширина <input aria-label="Ширина объекта" data-property="w" type="range" min="2" max="200" step="0.1"><output></output></label>
      <label>Высота <input aria-label="Высота объекта" data-property="h" type="range" min="2" max="200" step="0.1"><output></output></label>
      <label>Поворот <input aria-label="Поворот объекта" data-property="angle" type="range" min="-180" max="180" step="1"><output></output></label>
    </details>
    <p>Тяните объект — положение · ↘ — размер · ↻ — поворот<br>Стрелки — сдвиг; Shift — быстрее. Макет сохранится в этом браузере.</p>`;
  root.append(tools);
  const footer = document.createElement("div");
  footer.className = "promo-editor-actions";
  footer.innerHTML = `<p role="status"></p><button type="button" data-action="cancel">Отмена</button><button type="button" data-action="save">Сохранить дизайн</button>`;
  root.append(footer);
  document.body.append(root);
  document.body.classList.add("promo-editor-open");
  const elements = promoElements(card);
  // Snapshot the existing responsive composition before making it editable.
  let layout = readPromoLayout();
  if (!layout) {
    layout = { version: 1, textScale: 1, parts: {} };
    elements.forEach((element, index) => {
      const rect = element.getBoundingClientRect();
      layout.parts[PROMO_PARTS[index]] = {
        x: (rect.x + rect.width / 2) / innerWidth * 100,
        y: (rect.y + rect.height / 2) / innerHeight * 100,
        w: element.offsetWidth / innerWidth * 100,
        h: element.offsetHeight / innerHeight * 100,
        angle: index < 4 ? [-2, 2, 1.5, -1.5][index] : 0,
      };
    });
  }
  applyPromoLayout(card, layout);
  const [objectSelect, textSelect] = tools.querySelectorAll("select");
  textSelect.value = String(layout.textScale);
  let selected = 0;
  function syncControls() {
    const part = layout.parts[PROMO_PARTS[selected]];
    tools.querySelectorAll("[data-property]").forEach(input => {
      input.value = String(part[input.dataset.property]);
      input.nextElementSibling.textContent = `${Math.round(Number(input.value))}${input.dataset.property === "angle" ? "°" : "%"}`;
    });
  }
  function select(index) {
    selected = index;
    objectSelect.value = String(index);
    elements.forEach((element, i) => element.classList.toggle("is-selected", i === index));
    syncControls();
  }
  tools.querySelectorAll("[data-property]").forEach(input => {
    input.addEventListener("input", () => {
      const part = layout.parts[PROMO_PARTS[selected]];
      const property = input.dataset.property;
      part[property] = Number(input.value);
      if (selected === 5 && property !== "angle") {
        const side = property === "w" ? part.w / 100 * innerWidth : part.h / 100 * innerHeight;
        part.w = clamp(side / innerWidth * 100, 2, 200);
        part.h = clamp(side / innerHeight * 100, 2, 200);
      }
      applyPromoLayout(card, layout);
      syncControls();
    });
  });
  objectSelect.addEventListener("change", () => select(Number(objectSelect.value)));
  textSelect.addEventListener("change", () => {
    layout.textScale = Number(textSelect.value);
    applyPromoLayout(card, layout);
  });
  elements.forEach((element, index) => {
    element.classList.add("promo-editable");
    element.tabIndex = 0;
    element.setAttribute("aria-label", labels[index]);
    for (const [mode, symbol, name] of [["resize", "↘", "Изменить размер"], ["rotate", "↻", "Повернуть"]]) {
      const handle = document.createElement("button");
      handle.type = "button";
      handle.className = `promo-editor-handle ${mode}`;
      handle.dataset.mode = mode;
      handle.textContent = symbol;
      handle.setAttribute("aria-label", `${name}: ${labels[index]}`);
      element.append(handle);
    }
    element.addEventListener("focusin", () => select(index));
    element.addEventListener("pointerdown", event => {
      if (event.button !== 0) return;
      event.preventDefault();
      select(index);
      element.focus({ preventScroll: true });
      element.setPointerCapture(event.pointerId);
      const mode = event.target.closest("[data-mode]")?.dataset.mode ?? "move";
      const original = { ...layout.parts[PROMO_PARTS[index]] };
      const start = { x: event.clientX, y: event.clientY };
      const cx = original.x / 100 * innerWidth, cy = original.y / 100 * innerHeight;
      const startAngle = Math.atan2(start.y - cy, start.x - cx);
      const radians = original.angle * Math.PI / 180;
      function move(e) {
        const part = layout.parts[PROMO_PARTS[index]];
        const dx = e.clientX - start.x, dy = e.clientY - start.y;
        if (mode === "move") {
          part.x = clamp(original.x + dx / innerWidth * 100, 0, 100);
          part.y = clamp(original.y + dy / innerHeight * 100, 0, 100);
        } else if (mode === "resize") {
          const localX = dx * Math.cos(radians) + dy * Math.sin(radians);
          const localY = -dx * Math.sin(radians) + dy * Math.cos(radians);
          part.w = clamp(original.w + 2 * localX / innerWidth * 100, 2, 200);
          part.h = clamp(original.h + 2 * localY / innerHeight * 100, 2, 200);
          if (index === 5) {
            const side = Math.max(32, Math.min(part.w / 100 * innerWidth, part.h / 100 * innerHeight));
            part.w = side / innerWidth * 100;
            part.h = side / innerHeight * 100;
          }
        } else {
          const angle = original.angle + (Math.atan2(e.clientY - cy, e.clientX - cx) - startAngle) * 180 / Math.PI;
          part.angle = ((angle + 540) % 360) - 180;
        }
        applyPromoLayout(card, layout);
        syncControls();
      }
      function end() {
        element.removeEventListener("pointermove", move);
        element.removeEventListener("pointerup", end);
        element.removeEventListener("pointercancel", end);
        element.removeEventListener("lostpointercapture", end);
      }
      element.addEventListener("pointermove", move);
      element.addEventListener("pointerup", end);
      element.addEventListener("pointercancel", end);
      element.addEventListener("lostpointercapture", end);
    });
    element.addEventListener("keydown", event => {
      const step = event.shiftKey ? 1 : 0.1;
      const delta = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[event.key];
      if (!delta || event.target !== element) return;
      event.preventDefault();
      const part = layout.parts[PROMO_PARTS[index]];
      part.x = clamp(part.x + delta[0], 0, 100);
      part.y = clamp(part.y + delta[1], 0, 100);
      applyPromoLayout(card, layout);
    });
  });
  function close() {
    root.remove();
    document.body.classList.remove("promo-editor-open");
    onClose();
    if (previousFocus?.isConnected) previousFocus.focus();
  }
  root.addEventListener("keydown", event => {
    if (event.key === "Escape") close();
    if (event.key === "Tab") {
      const focusables = [...root.querySelectorAll('select, button, input, summary, [tabindex="0"]')].filter(el => el.getClientRects().length);
      const first = focusables[0], last = focusables.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  footer.querySelector('[data-action="cancel"]').onclick = close;
  footer.querySelector('[data-action="save"]').onclick = () => {
    try { localStorage.setItem(PROMO_LAYOUT_KEY, JSON.stringify(layout)); }
    catch {
      footer.querySelector('[role="status"]').textContent = "Не удалось сохранить дизайн. Разрешите хранение данных в браузере и повторите.";
      return;
    }
    close();
  };
  select(selected);
  objectSelect.focus();
}
