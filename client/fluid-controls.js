/** In-browser visual tuning for the public hero; no saved or server settings. */
const form = document.querySelector("#fluid-controls");
const fluid = document.querySelector(".fm-public-hero .fm-fluid");
const units = { size: "%", drift: "px", turn: "deg", blur: "px" };
const labels = { size: "%", drift: " px", speed: "×", turn: "°", blur: " px" };
function apply() {
  for (const input of form.querySelectorAll('input[type="range"]')) {
    const value = Number(input.value);
    form.querySelector(`output[for="${input.id}"]`).value = `${value}${labels[input.name]}`;
    if (input.name === "speed") {
      // Preserve the animation position while changing its rate. Existing CSS
      // already includes the global 0.4× and initial local 1.4× speeds.
      for (const spot of fluid.children) {
        for (const animation of spot.getAnimations()) {
          if (animation.animationName === "fm-fluid-drift") animation.updatePlaybackRate(value / 1.4);
        }
      }
    } else {
      fluid.style.setProperty(`--fm-fluid-${input.name}`, `${value}${units[input.name]}`);
      if (input.name === "size") fluid.style.setProperty("--fm-fluid-size-number", String(value));
    }
  }
}
form.addEventListener("input", apply);
form.addEventListener("submit", event => event.preventDefault());
form.addEventListener("reset", () => requestAnimationFrame(apply));
const reduced = matchMedia("(prefers-reduced-motion: reduce)");
function motionPreference() {
  document.querySelector("#fluid-motion-note").hidden = !reduced.matches;
  requestAnimationFrame(apply);
}
reduced.addEventListener("change", motionPreference);
motionPreference();
