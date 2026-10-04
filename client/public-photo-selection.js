// Selection is browser state; price and free entitlement remain server-owned.
export function createPhotoSelection({ resultId, requestQuote, onChange }) {
  const selected = new Set();
  let revision = 0, quote = null, status = 'empty';
  const snapshot = () => ({ result_id: resultId, photo_ids: [...selected], quote, status });
  async function update(ids) {
    selected.clear(); for (const id of ids) selected.add(id);
    const current = ++revision;
    quote = null; status = selected.size ? 'pending' : 'empty'; onChange(snapshot());
    if (!selected.size) return;
    try {
      const response = await requestQuote({ result_id: resultId, photo_ids: [...selected] });
      if (current !== revision) return;
      if (response.currency !== 'RUB' || !Number.isInteger(response.total_kopecks) || response.total_kopecks < 0 || response.selected_count !== selected.size) throw new Error('invalid_quote');
      quote = response; status = 'ready';
    } catch { if (current !== revision) return; status = 'error'; }
    onChange(snapshot());
  }
  return {
    snapshot,
    set(id, checked) { const ids = new Set(selected); if (checked) ids.add(id); else ids.delete(id); return update(ids); },
    setAll(ids, checked) { const next = new Set(selected); for (const id of ids) { if (checked) next.add(id); else next.delete(id); } return update(next); },
    clear() { return update([]); },
  };
}

export function mountPhotoSelection(summary) {
  const count = summary.querySelector('#photo-selection-count');
  const total = summary.querySelector('#photo-selection-total');
  const download = summary.querySelector('#photo-selection-download');
  let controller = null, rows = [], groups = [];
  function paint(state) {
    summary.dispatchEvent(new CustomEvent('photo-selection-change', { detail: state }));
    count.textContent = `Выбрано: ${state.photo_ids.length}`;
    total.textContent = state.status === 'ready' ? `${new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(state.quote.total_kopecks / 100)} ₽` : ({empty:'Выберите фотографии',pending:'Рассчитываем стоимость…',error:'Не удалось рассчитать стоимость. Повторите.'})[state.status];
    download.disabled = state.status !== 'ready';
    summary.querySelector('#photo-selection-retry').hidden = state.status !== 'error';
    for (const row of rows) row.input.checked = state.photo_ids.includes(row.id);
    for (const group of groups) {
      const available = group.rows.filter(row => !row.input.disabled);
      const checked = available.filter(row => row.input.checked).length;
      group.input.checked = available.length > 0 && checked === available.length;
      group.input.indeterminate = checked > 0 && checked < available.length;
      group.input.disabled = !available.length;
    }
  }
  summary.querySelector('#photo-selection-retry').addEventListener('click', () => { if (controller) void controller.setAll([], true); });
  download.addEventListener('click', () => {
    const state = controller?.snapshot();
    if (state?.status === 'ready') summary.dispatchEvent(new CustomEvent('photo-selection-download', { bubbles: true, detail: { result_id: state.result_id, photo_ids: state.photo_ids, quote: state.quote } }));
  });
  return {
    clear() { controller?.clear(); controller = null; rows = []; groups = []; summary.hidden = true; },
    start(result) {
      controller?.clear(); rows = []; groups = [];
      controller = createPhotoSelection({ resultId: result.result_id, onChange: paint, requestQuote: async body => {
        const response = await fetch('/api/public/quote', { method:'POST', credentials:'same-origin', cache:'no-store', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
        if (!response.ok) throw new Error('quote_failed'); return response.json();
      }});
      summary.hidden = false; paint(controller.snapshot());
      return {
        venue(section) {
          const label = document.createElement('label'); label.className = 'fm-photo-select-all';
          const input = document.createElement('input'); input.type = 'checkbox'; label.append(input, document.createTextNode('Выбрать все доступные фото площадки')); section.append(label);
          const group = { input, rows: [] }; groups.push(group);
          input.addEventListener('change', () => void controller.setAll(group.rows.filter(row => !row.input.disabled).map(row => row.id), input.checked));
          return group;
        },
        photo(figure, photo, group) {
          const label = document.createElement('label'); label.className = `fm-photo-select ${photo.is_free ? 'fm-photo-select-free' : 'fm-photo-select-paid'}`;
          const input = document.createElement('input'); input.type = 'checkbox'; input.setAttribute('aria-label', `Выбрать фото ${photo.visit_date}`);
          label.append(input, document.createTextNode(photo.is_free ? 'Бесплатно' : 'Выбрать фото')); figure.append(label);
          const row = { id: photo.id, input }; rows.push(row); group.rows.push(row);
          input.addEventListener('change', () => void controller.set(photo.id, input.checked));
          return () => { input.disabled = true; void controller.set(photo.id, false); };
        },
        complete() { paint(controller.snapshot()); },
      };
    },
  };
}
