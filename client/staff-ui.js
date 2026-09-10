import { watchRollingCount } from "./motion-ui.js";

const page = document.body.dataset.staffPage;
const roles = { photographer: "Фотограф", operator: "Оператор", developer: "Разработчик" };

async function loadIdentity() {
  if (page === "login") return;
  try {
    const response = await fetch("/api/staff/session", { credentials: "same-origin", cache: "no-store" });
    if (response.status === 401) { window.location.assign("/staff/login"); return; }
    if (!response.ok) return;
    const identity = await response.json();
    const accountName = document.querySelector("#staff-account-name");
    accountName.textContent = identity.username;
    accountName.title = identity.username;
    accountName.classList.toggle("fm-account-name-privileged", ["operator", "developer"].includes(identity.role));
    accountName.hidden = false;
    document.querySelector("#staff-identity").textContent = `${identity.username} · ${roles[identity.role] ?? identity.role}`;
    document.querySelectorAll("[data-staff-roles]").forEach(link => {
      link.hidden = !link.dataset.staffRoles.split(" ").includes(identity.role);
    });
  } catch { /* Page content is still usable; identity has no write authority. */ }
}

document.querySelector("#staff-logout")?.addEventListener("click", async event => {
  const button = event.currentTarget;
  button.disabled = true;
  const csrf = document.cookie.split(";").map(value => value.trim()).find(value => value.startsWith("fm_staff_csrf="))?.slice("fm_staff_csrf=".length) ?? "";
  try {
    const response = await fetch("/api/staff/session", { method: "DELETE", credentials: "same-origin", headers: { "X-CSRF-Token": decodeURIComponent(csrf) } });
    if (response.ok || response.status === 401) window.location.assign("/staff/login");
    else button.textContent = "Не удалось выйти. Повторить";
  } catch { button.textContent = "Не удалось выйти. Повторить"; }
  finally { button.disabled = false; }
});

const accountMenu = document.querySelector(".fm-account-dropdown");
document.addEventListener("click", event => {
  if (accountMenu && !accountMenu.contains(event.target)) accountMenu.open = false;
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && accountMenu?.open) {
    accountMenu.open = false;
    accountMenu.querySelector("summary").focus();
  }
});

for (const table of document.querySelectorAll("main table")) {
  const scroller = document.createElement("div");
  scroller.className = "fm-table-scroll";
  scroller.tabIndex = 0;
  scroller.setAttribute("role", "region");
  scroller.setAttribute("aria-label", table.caption?.textContent || "Таблица данных");
  table.before(scroller); scroller.append(table);
}
for (const element of document.querySelectorAll('[data-rolling-count], #queue-pending, #queue-processing, #queue-ready, #queue-no-faces, #queue-failed, #slo-population, #slo-success-under-15-minutes, #slo-breach, #slo-open')) {
  watchRollingCount(element);
}
document.querySelectorAll("[data-copy-token]").forEach(button => button.addEventListener("click", async () => {
  const token = button.closest(".fm-token");
  try {
    await navigator.clipboard.writeText(token.querySelector("code").textContent);
    token.querySelector(".fm-copy-status").textContent = "Токен скопирован";
  } catch { token.querySelector(".fm-copy-status").textContent = "Не удалось скопировать. Выделите токен и скопируйте вручную."; }
}));
void loadIdentity();

for (const form of document.querySelectorAll('.fm-device-rename')) {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const status = form.querySelector('[role="status"]');
    const button = form.querySelector('button');
    const input = form.querySelector('[name="name"]');
    const name = input.value.trim();
    if (!name) { status.textContent = 'Введите название экрана.'; return; }
    button.disabled = true;
    const csrf = document.cookie.split(';').map(value => value.trim()).find(value => value.startsWith('fm_staff_csrf='))?.slice('fm_staff_csrf='.length) ?? '';
    try {
      const response = await fetch(`/api/serving/display-clients/${encodeURIComponent(form.dataset.clientId)}/name`, {
        method: 'PUT', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(csrf) },
        body: JSON.stringify({ name }),
      });
      if (!response.ok) throw new Error('rename_failed');
      const saved = await response.json();
      input.value = saved.name;
      form.closest('.fm-device-card').querySelector('h2').textContent = saved.name;
      for (const row of document.querySelectorAll('.fm-device-table tbody tr')) {
        if (row.querySelector('[data-field="display-client-id"]')?.textContent === form.dataset.clientId) {
          row.querySelector('[data-field="name"]').textContent = saved.name;
        }
      }
      status.textContent = 'Название сохранено. На клиенте откройте «Конфигурацию», чтобы увидеть его.';
    } catch { status.textContent = 'Не удалось сохранить название. Проверьте соединение и вход в аккаунт.'; }
    finally { button.disabled = false; }
  });
}
