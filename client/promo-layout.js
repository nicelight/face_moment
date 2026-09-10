/** Local kiosk composition only; no images, tickets or credentials are stored. */
export const PROMO_LAYOUT_KEY = "face-moment.promo-layout.v1";
export const PROMO_PARTS = ["photo-1", "photo-2", "photo-3", "photo-4", "text", "qr"];

export function validPromoLayout(value) {
  return value?.version === 1 && [0.75, 1, 1.4].includes(value.textScale) &&
    PROMO_PARTS.every(key => {
      const part = value.parts?.[key];
      return part && ["x", "y", "w", "h", "angle"].every(k => Number.isFinite(part[k])) &&
        part.x >= -50 && part.x <= 150 && part.y >= -50 && part.y <= 150 &&
        part.w >= 2 && part.w <= 200 && part.h >= 2 && part.h <= 200 &&
        Math.abs(part.angle) <= 180;
    });
}

export function readPromoLayout() {
  try {
    const value = JSON.parse(globalThis.localStorage.getItem(PROMO_LAYOUT_KEY));
    return validPromoLayout(value) ? value : null;
  } catch { return null; }
}

export function promoElements(card) {
  return [...card.querySelectorAll(".promo-photo-card"),
    card.querySelector(".promo-copy h2"), card.querySelector(".promo-qr-panel")];
}

export function applyPromoLayout(card, layout) {
  card.classList.add("promo-custom-layout");
  card.style.setProperty("--promo-text-scale", layout.textScale);
  promoElements(card).forEach((element, index) => {
    const part = layout.parts[PROMO_PARTS[index]];
    element.dataset.layoutPart = PROMO_PARTS[index];
    Object.assign(element.style, {
      left: `${part.x}%`, top: `${part.y}%`,
      width: index === 5 ? `min(${part.w}vw, ${part.h}dvh)` : `${part.w}%`,
      height: index === 5 ? `min(${part.w}vw, ${part.h}dvh)` : `${part.h}%`,
      transform: `translate(-50%, -50%) rotate(${part.angle}deg)`,
    });
  });
}

export function applySavedPromoLayout(card) {
  const layout = readPromoLayout();
  if (layout) applyPromoLayout(card, layout);
}
