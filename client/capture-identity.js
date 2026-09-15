// Manual labels persist; evaluation controls deliberately live only in the DOM.
const reasons = {
  recognized: '', no_face: 'Сервер не нашёл лицо в crop',
  preparation_unavailable: 'Подготовка embedding недоступна или не завершена',
  preparation_failed: 'Ошибка подготовки embedding',
  incompatible_revision: 'Другая версия модели',
  no_compatible_examples: 'Нет размеченных примеров совместимой версии модели',
  below_threshold: 'Сходство ниже порога площадки',
};

function element(tag, text = '', className = '') {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function api(path, method = 'GET', body) {
  const csrf = document.cookie.split(';').map(value => value.trim())
    .find(value => value.startsWith('fm_staff_csrf='))?.slice('fm_staff_csrf='.length) || '';
  const response = await fetch(`/api/diagnostics/${path}`, {
    method, credentials: 'same-origin', cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(csrf) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) throw new Error(response.status === 401 ? 'Сессия завершилась. Войдите заново.'
    : response.status === 403 ? 'Недостаточно прав или сессия устарела.'
      : 'Не удалось выполнить действие. Проверьте подключение и повторите.');
  return response.json();
}

export function createCaptureDiagnostics(root) {
  let people = [];
  let captureRequest = 0;
  const error = root.querySelector('#identity-error');
  const peopleContainer = root.querySelector('#identity-people');
  const captureContainer = root.querySelector('#capture-attempts');
  const captureStatus = root.querySelector('#captures-status');
  const report = reason => { error.textContent = reason.message || String(reason); };

  function personOptions(select, value = '', allowCreate = false) {
    select.replaceChildren(new Option('Не выбран', ''));
    for (const person of people) select.add(new Option(`${person.name} · ${person.id.slice(-6)}`, person.id));
    if (allowCreate) select.add(new Option('+ Новый человек…', '__new'));
    select.value = value;
    if (!select.value) select.value = '';
  }

  async function refreshPeople() {
    people = (await api('people')).people;
    peopleContainer.replaceChildren();
    for (const person of people) {
      const row = element('div', '', 'fm-identity-person');
      const name = element('input'); name.value = person.name; name.maxLength = 200;
      name.setAttribute('aria-label', `Имя человека ${person.name}`);
      const marker = element('small', person.id.slice(-6));
      const save = element('button', 'Переименовать'); save.type = 'button';
      save.onclick = async () => {
        try { await api(`people/${person.id}`, 'PATCH', { name: name.value }); await refreshPeople(); }
        catch (reason) { report(reason); }
      };
      const remove = element('button', 'Удалить человека'); remove.type = 'button';
      remove.onclick = async () => {
        if (!window.confirm(`Удалить «${person.name}» и всю его разметку? Фотографии останутся.`)) return;
        try { await api(`people/${person.id}`, 'DELETE'); await refreshPeople(); }
        catch (reason) { report(reason); }
      };
      row.append(name, marker, save, remove); peopleContainer.append(row);
    }
    root.querySelectorAll('select[data-person-select]').forEach(select => {
      personOptions(select, select.value, select.dataset.personSelect === 'label');
    });
  }

  const ready = refreshPeople().catch(report);
  root.querySelector('#identity-person-create').onsubmit = async event => {
    event.preventDefault(); const form = event.currentTarget;
    try {
      await api('people', 'POST', { name: form.elements.name.value });
      form.reset(); await refreshPeople(); error.textContent = '';
    } catch (reason) { report(reason); }
  };

  function addPhotoFaces(container, photo) {
    const details = element('details', '', 'fm-identity-faces');
    details.append(element('summary', 'Разметить лица'));
    const faces = element('div', '', 'fm-capture-grid'); details.append(faces);
    let loaded = false;
    details.ontoggle = async () => {
      if (!details.open || loaded) return;
      faces.textContent = 'Загружаем лица…';
      try {
        await ready;
        const payload = await api(`photo-faces/${photo.photo_id}`);
        faces.replaceChildren();
        for (const face of payload.faces) {
          const card = element('div', '', 'fm-capture-card');
          const image = element('img'); image.src = face.image_url; image.alt = 'Найденное лицо на фотографии'; image.loading = 'lazy';
          const select = element('select'); select.dataset.personSelect = 'label';
          select.setAttribute('aria-label', 'Кто на фотографии');
          personOptions(select, face.person_id || '', true);
          const saved = element('small', face.person_id ? 'Размечено' : 'Без разметки');
          select.onchange = async () => {
            const previous = face.person_id || ''; select.disabled = true;
            try {
              let personId = select.value;
              if (personId === '__new') {
                const name = window.prompt('Имя нового человека. Одинаковое имя не объединяет людей.');
                if (!name?.trim()) { select.value = previous; return; }
                const person = await api('people', 'POST', { name });
                personId = person.id; await refreshPeople(); select.value = personId;
              }
              await api(`photo-faces/${face.id}/person`, 'PUT', { person_id: personId || null });
              face.person_id = personId || null;
              saved.textContent = personId ? 'Разметка сохранена' : 'Разметка удалена'; error.textContent = '';
            } catch (reason) { select.value = previous; report(reason); }
            finally { select.disabled = false; }
          };
          card.append(image, select, saved); faces.append(card);
        }
        if (!payload.faces.length) faces.textContent = 'Для этой версии обработки найденных лиц нет.';
        loaded = true;
      } catch (reason) { faces.textContent = 'Не удалось загрузить лица. Закройте и откройте блок для повтора.'; report(reason); }
    };
    container.append(details);
  }

  function cropCard(crop, data) {
    const card = element('div', '', 'fm-capture-card');
    if (crop.image_url) {
      const image = element('img'); image.src = crop.image_url; image.alt = 'JPEG обнаруженного лица'; image.loading = 'lazy';
      image.onerror = () => { image.replaceWith(element('p', 'Изображение недоступно')); }; card.append(image);
    } else card.append(element('p', data.images_expired ? 'Срок хранения изображения истёк' : 'Изображение не сохранено'));
    if (crop.rank) card.append(element('small', `Позиция в серверном отборе: ${crop.rank}`));
    card.append(element('strong', crop.person_id
      ? `${crop.identity_name} · ${crop.person_id.slice(-6)}` : 'Не распознан'));
    if (reasons[crop.reason]) card.append(element('p', reasons[crop.reason]));
    if (crop.score !== null) card.append(element('small', `Сходство: ${Number(crop.score).toFixed(3)} · порог: ${Number(data.threshold).toFixed(3)}`));
    if (crop.nearest_people?.length) {
      card.append(element('p', 'Ближайшие люди:'));
      const list = element('ol');
      for (const person of crop.nearest_people.slice(0, 3)) {
        list.append(element('li', `${person.identity_name} · ${person.person_id.slice(-6)} — ${Number(person.score).toFixed(3)}`));
      }
      card.append(list);
    }
    if (crop.person_id) {
      const label = element('label', 'Оценка предложения '); const evaluation = element('select');
      evaluation.add(new Option('Без оценки', '')); evaluation.add(new Option('Верно', 'correct')); evaluation.add(new Option('Неверно', 'false'));
      label.append(evaluation); card.append(label);
    }
    return card;
  }

  function renderCaptureDetails(container, payload) {
    container.replaceChildren(); const data = payload.captures;
    if (!data) {
      container.append(element('p', 'Изображения этого захвата не сохранены: старый Attempt или диагностическая запись недоступна.')); return;
    }
    container.append(element('p', `Порог сходства: ${Number(data.threshold).toFixed(3)} · модель: ${data.pipeline_revision_id}`));
    const selected = data.items.filter(item => item.rank !== null).sort((a, b) => a.rank - b.rank);
    const others = data.items.filter(item => item.rank === null).sort((a, b) => a.occurrence_index - b.occurrence_index);
    if (!data.selection_available) container.append(element('p', 'Фактический серверный отбор недоступен: обработка не дошла до завершения отбора.'));
    const groups = data.selection_available
      ? [['Выбраны для поиска', selected], ['Остальные обнаружения', others]]
      : [['Все присланные обнаружения', [...data.items].sort((a, b) => a.occurrence_index - b.occurrence_index)]];
    for (const [title, items] of groups) {
      container.append(element('h3', title)); const grid = element('div', '', 'fm-capture-grid');
      grid.append(...items.map(crop => cropCard(crop, data)));
      if (!items.length) grid.append(element('p', 'Нет обнаружений')); container.append(grid);
    }
    const missed = element('fieldset'); missed.append(element('legend', 'Кого не нашли'));
    for (let index = 0; index < 3; index += 1) {
      const label = element('label', `Человек ${index + 1} `);
      const select = element('select'); select.dataset.personSelect = 'missed'; personOptions(select);
      label.append(select); missed.append(label);
    }
    const clear = element('button', 'Очистить оценки захвата'); clear.type = 'button';
    clear.onclick = () => container.querySelectorAll('select').forEach(select => { select.value = ''; });
    container.append(missed, clear);
  }

  async function loadCaptures(query) {
    const current = ++captureRequest; captureStatus.textContent = 'Загружаем захваты…'; captureContainer.replaceChildren();
    try {
      const payload = await api(`captures?${query}`); await ready;
      if (current !== captureRequest) return;
      for (const attempt of payload.attempts) {
        const details = element('details', '', 'fm-capture-attempt');
        details.append(element('summary', `${StaffDateTime.formatTimestamp(attempt.created_at)} · Attempt ${attempt.id} · лиц: ${attempt.proposal_count}`));
        const content = element('div'); details.append(content); let loaded = false;
        details.ontoggle = async () => {
          if (!details.open || loaded) return;
          content.textContent = 'Загружаем детали…';
          try { renderCaptureDetails(content, await api(`captures/${attempt.id}`)); loaded = true; }
          catch (reason) { content.textContent = 'Детали недоступны. Закройте и откройте блок для повтора.'; report(reason); }
        };
        captureContainer.append(details);
      }
      captureStatus.textContent = payload.attempts.length ? `Захватов: ${payload.attempts.length}` : 'За выбранный период захватов нет.';
    } catch (reason) {
      if (current === captureRequest) { captureStatus.textContent = 'Не удалось загрузить захваты.'; report(reason); }
    }
  }
  return { addPhotoFaces, loadCaptures };
}
