for (const form of document.querySelectorAll('[data-spa-search]')) {
  const toggle = form.elements.namedItem('search_today');
  const dates = form.querySelector('[data-manual-dates]');
  const from = form.elements.namedItem('date_from');
  const to = form.elements.namedItem('date_to');
  const status = form.querySelector('[role="status"]');
  const button = form.querySelector('button[type="submit"]');
  const syncMode = () => {
    dates.disabled = toggle.checked;
    status.textContent = '';
  };
  toggle.addEventListener('change', syncMode);
  syncMode();

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const searchToday = toggle.checked;
    const dateFrom = window.StaffDateTime.dateValue(from);
    const dateTo = window.StaffDateTime.dateValue(to);
    if (!searchToday && (!dateFrom || !dateTo || dateFrom > dateTo)) {
      status.textContent = 'Укажите обе даты: «С» не должна быть позже «По».';
      return;
    }
    const payload = { search_today: searchToday };
    if (!searchToday) {
      payload.date_from = dateFrom;
      payload.date_to = dateTo;
    }
    const csrf = document.cookie.split(';').map(value => value.trim())
      .find(value => value.startsWith('fm_staff_csrf='))?.slice('fm_staff_csrf='.length) ?? '';
    button.disabled = toggle.disabled = true;
    dates.disabled = true;
    status.textContent = 'Сохранение…';
    try {
      const response = await fetch(`/api/serving/spas/${encodeURIComponent(form.dataset.spaId)}/search-dates`, {
        method: 'PUT', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(csrf) },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error('save_failed');
      const saved = await response.json();
      toggle.checked = saved.search_today;
      window.StaffDateTime.setDate(from, saved.date_from || saved.today);
      window.StaffDateTime.setDate(to, saved.date_to || saved.today);
      status.textContent = 'Настройки поиска сохранены.';
    } catch {
      status.textContent = 'Не удалось сохранить. Проверьте соединение и права доступа и повторите.';
    } finally {
      button.disabled = toggle.disabled = false;
      dates.disabled = toggle.checked;
    }
  });
}
