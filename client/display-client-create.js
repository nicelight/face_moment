export function mountDisplayCreate(form) {
  const section = form.closest('section');
  const opener = document.querySelector('[data-show-display-create]');
  const cancel = form.querySelector('[data-cancel-display-create]');
  const submit = form.querySelector('button[type="submit"]');
  const status = form.querySelector('[role="status"]');
  opener.addEventListener('click', () => {
    section.hidden = false;
    opener.setAttribute('aria-expanded', 'true');
    form.elements.namedItem('name').focus();
  });
  cancel.addEventListener('click', () => {
    section.hidden = true;
    form.reset();
    status.textContent = '';
    opener.setAttribute('aria-expanded', 'false');
    opener.focus();
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submit.disabled) return;
    const name = form.elements.namedItem('name').value.trim();
    const spaId = form.elements.namedItem('spa_id').value;
    if (!name || !spaId) {
      status.textContent = 'Введите название и выберите площадку.';
      return;
    }
    const csrf = document.cookie.split(';').map(value => value.trim())
      .find(value => value.startsWith('fm_staff_csrf='))?.slice('fm_staff_csrf='.length) ?? '';
    submit.disabled = cancel.disabled = true;
    status.textContent = 'Создание…';
    try {
      const response = await fetch('/api/serving/display-clients', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(csrf) },
        body: JSON.stringify({ name, spa_id: spaId }),
      });
      if (!response.ok) {
        const messages = { 401: 'Войдите в аккаунт заново.', 403: 'Нет прав на создание экрана. Обновите страницу.',
          404: 'Площадка не найдена. Обновите список.', 409: 'Площадка отключена. Выберите другую.',
          422: 'Проверьте название и выбранную площадку.' };
        status.textContent = messages[response.status] || 'Не удалось создать экран. Проверьте список перед повторной попыткой.';
        return;
      }
      window.location.reload();
    } catch {
      status.textContent = 'Соединение прервано. Обновите список экранов перед повторной попыткой.';
    } finally {
      submit.disabled = cancel.disabled = false;
    }
  });
}

for (const form of document.querySelectorAll('[data-display-create]')) mountDisplayCreate(form);
