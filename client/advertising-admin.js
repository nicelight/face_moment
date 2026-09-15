const root = document.querySelector('[data-ad-spa]');
if (root) {
  const base = `/api/advertising/${root.dataset.adSpa}`;
  const form = root.querySelector('#ad-settings');
  const upload = root.querySelector('#ad-upload');
  const rows = root.querySelector('#ad-items');
  const status = root.querySelector('#ad-status');
  const error = root.querySelector('#ad-error');
  let playlist = null;
  let items = [];
  let busy = false;

  function csrf() {
    return decodeURIComponent(document.cookie.split('; ').find(value => value.startsWith('fm_staff_csrf='))?.split('=').slice(1).join('=') ?? '');
  }

  async function request(url, options = {}) {
    const response = await fetch(url, { ...options, headers: { 'X-CSRF-Token': csrf(), ...options.headers } });
    if (!response.ok) {
      let message;
      try { message = (await response.json()).detail; } catch { /* use status */ }
      throw new Error(typeof message === 'string' ? message : `Не удалось выполнить действие (HTTP ${response.status}).`);
    }
    return response.json();
  }

  function accept(next, { preserveDraft = false } = {}) {
    if (preserveDraft) {
      const fresh = new Map(next.items.map(item => [item.id, item]));
      items = items.filter(item => fresh.has(item.id)).map(item => fresh.get(item.id));
      const present = new Set(items.map(item => item.id));
      items.push(...next.items.filter(item => !present.has(item.id)));
    } else {
      items = next.items;
      form.elements.image_seconds.value = next.image_seconds;
      form.elements.crossfade_seconds.value = next.crossfade_seconds;
      form.elements.random_start.checked = next.random_start;
    }
    playlist = next;
    render();
  }

  function total() {
    const imageSeconds = Number(form.elements.image_seconds.value) || 0;
    let seconds = 0, unknown = false;
    for (const item of items) {
      if (item.content_type.startsWith('image/')) seconds += imageSeconds;
      else if (item.duration_seconds) seconds += item.duration_seconds;
      else unknown = true;
    }
    root.querySelector('#ad-total').textContent = `Материалов: ${items.length} · ${(items.reduce((sum, item) => sum + item.byte_size, 0) / 1048576).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} MiB · Длительность: ${seconds.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} сек.${unknown ? ' + видео с неизвестной длительностью' : ''}`;
    rows.querySelectorAll('[data-image-duration]').forEach(cell => { cell.textContent = `${imageSeconds} сек.`; });
  }

  function cell(row, text = '') {
    const td = document.createElement('td');
    td.textContent = text;
    row.append(td);
    return td;
  }

  function render() {
    rows.replaceChildren();
    items.forEach((item, index) => {
      const row = document.createElement('tr');
      const preview = document.createElement('a');
      preview.className = 'ad-preview';
      preview.href = item.url;
      preview.target = '_blank';
      preview.rel = 'noopener';
      preview.setAttribute('aria-label', `Открыть ${item.filename}`);
      if (item.content_type === 'video/webm') {
        preview.classList.add('ad-video-preview');
        preview.textContent = '▶';
      } else {
        const img = document.createElement('img');
        img.src = item.url;
        img.alt = item.filename;
        img.loading = 'lazy';
        preview.append(img);
      }
      cell(row).append(preview);
      cell(row, item.filename).className = 'ad-filename';
      const duration = cell(row, item.duration_seconds ? `${item.duration_seconds.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} сек.` : 'Целиком');
      if (item.content_type.startsWith('image/')) duration.dataset.imageDuration = '';
      const position = document.createElement('select');
      position.setAttribute('aria-label', `Позиция ${item.filename}`);
      items.forEach((_, number) => position.add(new Option(String(number + 1), String(number))));
      position.value = String(index);
      position.disabled = busy;
      position.addEventListener('change', () => {
        const [moved] = items.splice(index, 1);
        items.splice(Number(position.value), 0, moved);
        render();
      });
      cell(row).append(position);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = 'Удалить';
      remove.disabled = busy;
      remove.addEventListener('click', () => run(async () => {
        accept(await request(`${base}/media/${item.id}`, { method: 'DELETE' }), { preserveDraft: true });
        status.textContent = 'Материал удалён. Порядок и настройки сохраняются отдельной кнопкой.';
      }));
      cell(row).append(remove);
      rows.append(row);
    });
    total();
  }

  async function run(operation) {
    if (busy) return;
    busy = true;
    error.textContent = '';
    root.querySelectorAll('button, input, select').forEach(element => { element.disabled = true; });
    try { await operation(); }
    catch (failure) { error.textContent = failure.message; }
    finally {
      busy = false;
      root.querySelectorAll('button, input, select').forEach(element => { element.disabled = false; });
    }
  }

  function videoDuration(file) {
    return new Promise(resolve => {
      const video = document.createElement('video');
      const url = URL.createObjectURL(file);
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        const duration = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : null;
        video.removeAttribute('src');
        video.load();
        URL.revokeObjectURL(url);
        resolve(duration);
      };
      const timer = setTimeout(finish, 5000);
      video.preload = 'metadata';
      video.onloadedmetadata = finish;
      video.onerror = finish;
      video.src = url;
    });
  }

  upload.addEventListener('submit', event => {
    event.preventDefault();
    const files = [...upload.elements.files.files];
    void run(async () => {
      const failures = [];
      for (const [index, file] of files.entries()) {
        status.textContent = `Загружаем ${index + 1}/${files.length}: ${file.name}`;
        try {
          const body = new FormData();
          body.append('file', file);
          if (/\.webm$/i.test(file.name)) {
            const duration = await videoDuration(file);
            if (duration !== null) body.append('duration_seconds', String(duration));
          }
          accept(await request(`${base}/media`, { method: 'POST', body }), { preserveDraft: true });
        } catch (failure) { failures.push(`${file.name}: ${failure.message}`); }
      }
      upload.reset();
      status.textContent = 'Загрузка завершена. Новые материалы добавлены в конец.';
      error.textContent = failures.join(' ');
    });
  });

  form.addEventListener('input', total);
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!playlist) return;
    const payload = { revision: playlist.revision, item_ids: items.map(item => item.id),
      image_seconds: Number(form.elements.image_seconds.value),
      crossfade_seconds: Number(form.elements.crossfade_seconds.value),
      random_start: form.elements.random_start.checked };
    void run(async () => {
      accept(await request(`${base}/playlist`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }));
      status.textContent = 'Порядок и настройки сохранены. Экраны проверяют изменения раз в 30 секунд.';
    });
  });
  void run(async () => { accept(await request(`${base}/playlist`)); status.textContent = ''; });
}
