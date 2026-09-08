/* Small, event-driven Motion Atlas primitives. No perpetual animation loop. */
const reduced = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)");
const finePointer = globalThis.matchMedia?.("(pointer: fine)");

export function setRollingCount(element, value) {
  const number = String(value);
  if (!/^\d+$/.test(number)) { element.textContent = number; return; }
  let counter = element.querySelector(".fm-count");
  if (counter?.dataset.value === number) return;
  if (!counter || counter.children.length !== number.length) {
    counter = document.createElement("span");
    counter.className = "fm-count";
    counter.setAttribute("role", "img");
    for (const digit of number) {
      const window = document.createElement("span");
      window.className = "fm-count-digit";
      window.setAttribute("aria-hidden", "true");
      const strip = document.createElement("span");
      strip.className = "fm-count-strip";
      for (let n = 0; n < 10; n += 1) {
        const item = document.createElement("span");
        item.textContent = String(n);
        strip.append(item);
      }
      // First render is the actual value, not an invented count-up from zero.
      strip.style.transform = `translateY(-${Number(digit) * 10}%)`;
      window.append(strip);
      counter.append(window);
    }
    element.replaceChildren(counter);
  }
  counter.dataset.value = number;
  counter.setAttribute("aria-label", number);
  [...counter.children].forEach((window, i) => {
    window.firstElementChild.style.transform = `translateY(-${Number(number[i]) * 10}%)`;
  });
}

export function watchRollingCount(element) {
  // Keep the previous digit strips across the existing page's text updates.
  let counter;
  const refresh = () => {
    if (element.firstElementChild?.classList.contains("fm-count")) return;
    const raw = element.textContent.trim();
    if (!/^\d+$/.test(raw)) { counter = null; return; }
    if (counter) element.replaceChildren(counter);
    setRollingCount(element, raw);
    counter = element.firstElementChild;
  };
  refresh();
  const observer = new MutationObserver(refresh);
  observer.observe(element, { childList: true, characterData: true });
  return () => observer.disconnect();
}

export function mountMotion(root = document) {
  root.addEventListener("click", event => {
    const target = event.target.closest?.("button, .fm-button");
    if (!target || target.disabled || reduced?.matches || target.id === "inventory-confirm-purge") return;
    if (!target.closest(".fm-page")) return;
    const bounds = target.getBoundingClientRect();
    const x = event.detail ? event.clientX - bounds.left : bounds.width / 2;
    const y = event.detail ? event.clientY - bounds.top : bounds.height / 2;
    while (target.querySelectorAll(".fm-ring").length > 6) target.querySelector(".fm-ring").remove();
    for (let i = 0; i < 3; i += 1) {
      const ring = document.createElement("i");
      ring.className = "fm-ring";
      ring.setAttribute("aria-hidden", "true");
      ring.style.left = `${x}px`; ring.style.top = `${y}px`;
      ring.style.animationDelay = `${i * 130 / .46}ms`;
      target.append(ring);
      ring.addEventListener("animationend", () => ring.remove(), { once: true });
      setTimeout(() => ring.remove(), 2500);
    }
  });

  const glow = document.createElement("div");
  glow.className = "fm-cursor-light"; glow.setAttribute("aria-hidden", "true");
  document.body.append(glow);
  let pending = 0, point;
  root.addEventListener("pointermove", event => {
    if (!finePointer?.matches || reduced?.matches || document.hidden || event.pointerType === "touch") return;
    point = { x: event.clientX, y: event.clientY, target: event.target.closest?.("[data-tilt]") };
    if (pending) return;
    pending = requestAnimationFrame(() => {
      pending = 0;
      glow.style.transform = `translate(${point.x - 250}px, ${point.y - 250}px)`;
      glow.classList.add("is-visible");
      if (point.target) {
        const rect = point.target.parentElement.getBoundingClientRect();
        const x = Math.max(0, Math.min(1, (point.x - rect.left) / rect.width));
        const y = Math.max(0, Math.min(1, (point.y - rect.top) / rect.height));
        point.target.style.transform = `perspective(750px) rotateX(${-(y - .5) * 36}deg) rotateY(${(x - .5) * 36}deg)`;
        point.target.style.setProperty("--mx", `${x * 100}%`);
        point.target.style.setProperty("--my", `${y * 100}%`);
      }
    });
  }, { passive: true });
  root.addEventListener("pointerout", event => {
    const target = event.target.closest?.("[data-tilt]");
    if (target && !target.contains(event.relatedTarget)) target.style.transform = "none";
    if (!event.relatedTarget) glow.classList.remove("is-visible");
  }, { passive: true });
  const pause = () => {
    document.body.classList.toggle("fm-motion-paused", document.hidden);
    if (document.hidden || reduced?.matches) {
      if (pending) cancelAnimationFrame(pending);
      pending = 0; glow.classList.remove("is-visible");
      root.querySelectorAll("[data-tilt]").forEach(el => { el.style.transform = "none"; });
    }
  };
  document.addEventListener("visibilitychange", pause);
  reduced?.addEventListener("change", pause);
  pause();
  if ("IntersectionObserver" in globalThis) {
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      entry.target.toggleAttribute("data-motion-paused", !entry.isIntersecting);
    }));
    root.querySelectorAll(".fm-fluid, .fm-aurora").forEach(el => observer.observe(el));
  }
}

if (typeof document !== "undefined") mountMotion();
