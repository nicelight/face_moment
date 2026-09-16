import { createCaptureDiagnostics } from './capture-identity.js';

const root = document.querySelector('[data-staff-media]');
if (root) {
  const diagnostics = root.dataset.captureDiagnostics === 'true' ? createCaptureDiagnostics(root) : null;
  const form = root.querySelector('#media-filter');
  const rows = root.querySelector('#media-rows');
  const status = root.querySelector('#media-status');
  const error = root.querySelector('#media-error');
  const submit = form.querySelector('button');
  const labels = { pending: 'В очереди', processing: 'Обрабатывается', ready: 'Готово', failed: 'Ошибка обработки' };
  let requestNumber = 0;

  function cell(row, value) {
    const td = document.createElement('td');
    td.textContent = value;
    row.append(td);
    return td;
  }

  function updateCount() {
    const count = rows.children.length;
    status.textContent = count ? `Фотографий: ${count}` : 'За выбранные даты фотографий нет.';
  }

  function renderPhoto(photo) {
    const row = document.createElement('tr');
    row.dataset.photoId = photo.photo_id;
    const previewCell = cell(row, '');
    const link = document.createElement('a');
    link.href = photo.original_url;
    link.target = '_blank';
    link.rel = 'noopener';
    link.className = 'fm-media-preview';
    link.setAttribute('aria-label', 'Открыть оригинал фотографии в новой вкладке');
    const placeholder = document.createElement('span');
    placeholder.className = 'fm-media-placeholder';
    placeholder.textContent = 'Превью недоступно\nОткрыть оригинал ↗';
    link.append(placeholder);
    if (photo.thumbnail_url) {
      const image = document.createElement('img');
      image.alt = 'Превью фотографии';
      image.loading = 'lazy';
      image.decoding = 'async';
      image.addEventListener('load', () => { placeholder.hidden = true; });
      image.addEventListener('error', () => { image.remove(); placeholder.hidden = false; });
      image.src = photo.thumbnail_url;
      link.append(image);
    }
    previewCell.append(link);
    diagnostics?.addPhotoFaces(previewCell, photo);
    cell(row, StaffDateTime.formatTimestamp(photo.accepted_at)).className = 'fm-media-date';
    cell(row, StaffDateTime.formatTimestamp(photo.captured_at)).className = 'fm-media-date';
    const dimensions = cell(row, `${photo.width} × ${photo.height}`);
    const size = document.createElement('small');
    size.textContent = `${(photo.original_byte_size / 1048576).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} МБ`;
    dimensions.append(size);
    const stateCell = cell(row, '');
    const badge = document.createElement('span');
    badge.className = 'fm-media-state';
    badge.dataset.state = photo.processing_status || 'unknown';
    badge.textContent = labels[photo.processing_status] || 'Статус недоступен';
    stateCell.append(badge);
    const actions = cell(row, '');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'fm-media-delete';
    button.textContent = 'Удалить';
    button.addEventListener('click', async () => {
      if (!window.confirm('Убрать эту фотографию из библиотеки и поиска? Её можно будет восстановить.')) return;
      button.disabled = true;
      error.textContent = '';
      const csrf = document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith('fm_staff_csrf='))?.slice('fm_staff_csrf='.length) || '';
      try {
        const response = await fetch(`/api/inventory/photos/${encodeURIComponent(photo.photo_id)}/visibility`, {
          method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(csrf) },
          body: JSON.stringify({ schema_version: 1, active: false }),
        });
        if (!response.ok) throw new Error(response.status === 401 ? 'Сессия завершилась. Войдите заново.' : 'Не удалось удалить фотографию. Повторите попытку.');
        row.remove();
        updateCount();
      } catch (reason) {
        error.textContent = reason.message || 'Не удалось удалить фотографию.';
      } finally { button.disabled = false; }
    });
    actions.append(button);
    return row;
  }

  async function load() {
    const from = StaffDateTime.dateValue(form.querySelector('#media-date-from'));
    const to = StaffDateTime.dateValue(form.querySelector('#media-date-to'));
    if (!from || !to || from > to) {
      error.textContent = 'Укажите корректный период: дата «По» не раньше даты «С».';
      return;
    }
    const currentRequest = ++requestNumber;
    error.textContent = '';
    status.textContent = 'Загружаем фотографии…';
    rows.replaceChildren();
    submit.disabled = true;
    root.setAttribute('aria-busy', 'true');
    try {
      const query = new URLSearchParams({ spa_id: root.dataset.spaId, date_from: from, date_to: to });
      diagnostics?.loadCaptures(query);
      const response = await fetch(`/api/inventory/venue-media?${query}`, { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error(response.status === 401 ? 'Сессия завершилась. Войдите заново.' : 'Не удалось загрузить фотографии. Повторите попытку.');
      const payload = await response.json();
      if (currentRequest !== requestNumber) return;
      rows.replaceChildren(...payload.photos.map(renderPhoto));
      updateCount();
    } catch (reason) {
      if (currentRequest !== requestNumber) return;
      status.textContent = '';
      error.textContent = reason.message || 'Не удалось загрузить фотографии.';
    } finally {
      if (currentRequest === requestNumber) {
        submit.disabled = false;
        root.setAttribute('aria-busy', 'false');
      }
    }
  }
  form.addEventListener('submit', event => { event.preventDefault(); load(); });
  const cleanupOpen = root.querySelector('#orphan-cleanup-open');
  if (cleanupOpen) {
    const dialog = root.querySelector('#orphan-cleanup-dialog');
    const cleanupStatus = root.querySelector('#orphan-cleanup-status');
    cleanupOpen.addEventListener('click', () => dialog.showModal());
    root.querySelector('#orphan-cleanup-cancel').addEventListener('click', () => dialog.close());
    root.querySelector('#orphan-cleanup-confirm').addEventListener('click', async () => {
      dialog.close();
      cleanupOpen.disabled = true;
      cleanupStatus.textContent = 'Очистка выполняется. Дождитесь результата.';
      const csrf = document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith('fm_staff_csrf='))?.slice('fm_staff_csrf='.length) || '';
      try {
        const response = await fetch('/api/inventory/orphan-originals/cleanup', {
          method: 'POST', credentials: 'same-origin', cache: 'no-store',
          headers: { 'X-CSRF-Token': decodeURIComponent(csrf) },
        });
        if (!response.ok) throw new Error(response.status === 409
          ? 'Очистка уже запущена.' : response.status === 401
            ? 'Сессия завершилась. Войдите заново.' : 'Очистка не завершилась. Повторите позже.');
        const result = await response.json();
        cleanupStatus.textContent = `Очистка завершена: проверено ${result.scanned}, удалено ${result.deleted} файлов.`;
      } catch (reason) {
        cleanupStatus.textContent = reason.message || 'Не удалось выполнить очистку.';
      } finally { cleanupOpen.disabled = false; }
    });
  }
  load();
}
