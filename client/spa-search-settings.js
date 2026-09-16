function csrfHeaders() {
  const csrf = document.cookie.split(';').map(value => value.trim())
    .find(value => value.startsWith('fm_staff_csrf='))?.slice('fm_staff_csrf='.length) ?? '';
  return { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(csrf) };
}

export function mountSearchDates(form) {
  const toggle = form.elements.namedItem('search_today');
  const dates = form.querySelector('[data-manual-dates]');
  const from = form.elements.namedItem('date_from');
  const to = form.elements.namedItem('date_to');
  const status = form.querySelector('[role="status"]');
  const button = form.querySelector('button[type="submit"]');
  const manual = form.querySelector('[data-manual-search]') ?? dates;
  let savedMode = toggle.checked;
  let savedFrom = window.StaffDateTime.dateValue(from);
  let savedTo = window.StaffDateTime.dateValue(to);
  const syncMode = () => {
    dates.disabled = toggle.checked;
    manual.hidden = toggle.checked;
  };
  syncMode();

  async function save({ modeChange = false } = {}) {
    const searchToday = toggle.checked;
    // Changing mode uses the last saved range, not an unfinished date draft.
    if (modeChange) {
      window.StaffDateTime.setDate(from, savedFrom);
      window.StaffDateTime.setDate(to, savedTo);
    }
    const dateFrom = window.StaffDateTime.dateValue(from);
    const dateTo = window.StaffDateTime.dateValue(to);
    if (!searchToday && (!dateFrom || !dateTo || dateFrom > dateTo)) {
      if (modeChange) toggle.checked = savedMode;
      syncMode();
      status.textContent = 'Укажите обе даты: «С» не должна быть позже «По».';
      return;
    }
    const payload = { search_today: searchToday };
    if (!searchToday) {
      payload.date_from = dateFrom;
      payload.date_to = dateTo;
    }
    syncMode();
    button.disabled = toggle.disabled = true;
    dates.disabled = true;
    status.textContent = 'Сохранение…';
    try {
      const response = await fetch(`/api/serving/spas/${encodeURIComponent(form.dataset.spaId)}/search-dates`, {
        method: 'PUT', credentials: 'same-origin', cache: 'no-store',
        headers: csrfHeaders(),
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error('save_failed');
      const saved = await response.json();
      toggle.checked = saved.search_today;
      savedMode = saved.search_today;
      window.StaffDateTime.setDate(from, saved.date_from || saved.today);
      window.StaffDateTime.setDate(to, saved.date_to || saved.today);
      savedFrom = window.StaffDateTime.dateValue(from);
      savedTo = window.StaffDateTime.dateValue(to);
      status.textContent = 'Настройки поиска сохранены.';
    } catch {
      if (modeChange) toggle.checked = savedMode;
      status.textContent = 'Не удалось сохранить. Проверьте соединение и права доступа и повторите.';
    } finally {
      button.disabled = toggle.disabled = false;
      syncMode();
    }
  }
  toggle.addEventListener('change', () => { void save({ modeChange: true }); });
  form.addEventListener('submit', event => {
    event.preventDefault();
    void save();
  });
}

export function mountDetectorThreshold(form) {
  const toggle = form.elements.namedItem('edit_threshold');
  const input = form.elements.namedItem('threshold');
  const button = form.querySelector('button[type="submit"]');
  const status = form.querySelector('[role="status"]');
  let savedValue = input.value;
  const syncEditing = () => {
    input.disabled = button.disabled = !toggle.checked;
    if (!toggle.checked) input.value = savedValue;
  };
  syncEditing();
  toggle.addEventListener('change', () => {
    syncEditing();
    status.textContent = '';
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!toggle.checked || toggle.disabled) return;
    const threshold = Number(input.value);
    if (!Number.isFinite(threshold) || threshold <= 0 || threshold > 1) {
      status.textContent = 'Введите порог больше 0 и не больше 1.';
      return;
    }
    toggle.disabled = input.disabled = button.disabled = true;
    status.textContent = 'Сохранение…';
    try {
      const response = await fetch(`/api/serving/spas/${encodeURIComponent(form.dataset.spaId)}/detector-thresholds/${form.dataset.detector}`, {
        method: 'PUT', credentials: 'same-origin', cache: 'no-store',
        headers: csrfHeaders(), body: JSON.stringify({ threshold }),
      });
      if (!response.ok) throw new Error('save_failed');
      const saved = await response.json();
      savedValue = String(saved.threshold);
      toggle.checked = false;
      status.textContent = 'Порог сохранён.';
    } catch {
      status.textContent = 'Не удалось сохранить. Проверьте соединение и права доступа и повторите.';
    } finally {
      toggle.disabled = false;
      syncEditing();
    }
  });
}

export async function mountSimilarityThreshold(form) {
  const toggle = form.elements.namedItem('edit_threshold');
  const input = form.elements.namedItem('threshold');
  const button = form.querySelector('button[type="submit"]');
  const status = form.querySelector('[role="status"]');
  const model = form.querySelector('[data-serving-model]');
  const url = `/api/serving/spas/${encodeURIComponent(form.dataset.spaId)}/similarity-threshold`;
  let snapshot = null;
  const syncEditing = () => {
    input.disabled = button.disabled = !snapshot || toggle.disabled || !toggle.checked;
    if (!toggle.checked && snapshot) input.value = String(snapshot.threshold);
  };
  toggle.addEventListener('change', () => {
    syncEditing();
    status.textContent = '';
  });
  const render = saved => {
    snapshot = saved;
    model.textContent = saved.pipeline_code;
    model.title = `Serving revision: ${saved.pipeline_revision_id}`;
    input.value = String(saved.threshold);
    toggle.checked = false;
    toggle.disabled = false;
    syncEditing();
  };
  try {
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store' });
    if (!response.ok) throw new Error('unavailable');
    render(await response.json());
    status.textContent = '';
  } catch {
    model.textContent = 'недоступна';
    status.textContent = 'Не удалось загрузить текущую модель или её настройки. Проверьте соединение и права доступа; обновите страницу.';
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!snapshot || button.disabled) return;
    const threshold = Number(input.value);
    if (!input.value.trim() || !Number.isFinite(threshold) || threshold < -1 || threshold > 1) {
      status.textContent = 'Введите число от −1 до 1.';
      return;
    }
    toggle.disabled = input.disabled = button.disabled = true;
    status.textContent = 'Сохранение…';
    let stale = false;
    try {
      const response = await fetch(url, {
        method: 'PUT', credentials: 'same-origin', cache: 'no-store', headers: csrfHeaders(),
        body: JSON.stringify({ threshold, pipeline_revision_id: snapshot.pipeline_revision_id,
          settings_revision: snapshot.settings_revision }),
      });
      stale = response.status === 409;
      if (!response.ok) throw new Error('save_failed');
      render(await response.json());
      status.textContent = 'Порог сходства сохранён.';
    } catch {
      status.textContent = stale
        ? 'Модель или настройки изменились. Обновите страницу перед сохранением.'
        : 'Не удалось сохранить. Проверьте соединение и права доступа и повторите.';
    } finally {
      toggle.disabled = stale;
      syncEditing();
    }
  });
}

export function mountSpaCreate(form) {
  const section = form.closest('section');
  const opener = document.querySelector('[data-show-spa-create]');
  const cancel = form.querySelector('[data-cancel-spa-create]');
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
    submit.disabled = cancel.disabled = true;
    status.textContent = 'Создание…';
    try {
      const response = await fetch('/api/serving/spas', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: csrfHeaders(),
        body: JSON.stringify({ name: form.elements.namedItem('name').value.trim(),
          timezone: form.elements.namedItem('timezone').value.trim() }),
      });
      if (!response.ok) {
        const messages = { 401: 'Войдите в аккаунт заново.', 403: 'Нет прав на создание площадки. Обновите страницу.',
          409: 'Общая модель недоступна. Проверьте настройки приложения.',
          503: 'Не удалось проверить модель SFace. Проверьте настройки SFACE_* и файлы YuNet/SFace. Площадка не создана.',
          422: 'Проверьте название и часовой пояс.' };
        status.textContent = messages[response.status] || 'Не удалось создать площадку. Проверьте список перед повторной попыткой.';
        return;
      }
      window.location.reload();
    } catch {
      status.textContent = 'Соединение прервано. Обновите список площадок перед повторной попыткой.';
    } finally {
      submit.disabled = cancel.disabled = false;
    }
  });
}

for (const form of document.querySelectorAll('[data-spa-create]')) mountSpaCreate(form);
for (const form of document.querySelectorAll('[data-similarity-threshold]')) void mountSimilarityThreshold(form);
for (const form of document.querySelectorAll('[data-spa-search]')) mountSearchDates(form);
for (const form of document.querySelectorAll('[data-detector-threshold]')) mountDetectorThreshold(form);
