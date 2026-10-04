// Browser consumes the selected quote and promo order API; the server owns price and delivery.
export function createPhotoDownload({ request, makeId = () => crypto.randomUUID(), onChange = () => {} }) {
  let attempt = null;
  const key = selection => JSON.stringify([selection.result_id, [...selection.photo_ids].sort()]);
  function select(selection) {
    const nextKey = key(selection);
    if (attempt && attempt.key !== nextKey) { attempt = null; onChange({ status: 'idle' }); }
  }
  async function start(selection) {
    select(selection);
    if (!selection.quote || selection.quote.total_kopecks !== 0 || selection.quote.paid_count !== 0 || !selection.photo_ids.length) return;
    if (!attempt) attempt = { key: key(selection), body: { result_id: selection.result_id, photo_ids: [...selection.photo_ids], client_request_id: makeId() }, order: null, busy: false };
    const current = attempt;
    if (current.busy) return;
    current.busy = true;
    onChange({ status: 'loading' });
    try {
      if (!current.order) current.order = await request('/api/public/orders', current.body);
      const order = await request(`/api/public/orders/${current.order.id}`);
      if (attempt !== current) return;
      if (order.total_kopecks !== 0) throw new Error('free_order_required');
      if (order.archive_status === 'failed') onChange({ status: 'failed' });
      else if (order.archive_status === 'ready' && order.download_url) onChange({ status: 'ready', download_url: order.download_url });
      else if (order.archive_status === 'requested' || order.archive_status === 'preparing') onChange({ status: 'preparing' });
      else onChange({ status: 'failed' });
    } catch { if (attempt === current) onChange({ status: 'error' }); }
    finally { current.busy = false; }
  }
  return { select, start };
}

export function mountPhotoDownload(summary, panel) {
  const message = panel.querySelector('#photo-download-status');
  const retry = panel.querySelector('#photo-download-retry');
  const link = panel.querySelector('#photo-download-link');
  let selection = null, deliveryRevision = 0;
  function paint(state) {
    deliveryRevision++;
    panel.hidden = state.status === 'idle';
    message.textContent = ({ loading: 'Проверяем архив…', preparing: 'Архив готовится. Повторите через 30 секунд.', failed: 'Не удалось подготовить архив. Обратитесь в поддержку.', error: 'Не удалось проверить архив. Повторите попытку. Если ошибка сохраняется, обратитесь в поддержку.', ready: 'Архив готов. Скачайте выбранные фотографии.' })[state.status] || '';
    retry.hidden = !['preparing', 'error', 'failed'].includes(state.status);
    retry.disabled = state.status === 'loading';
    link.hidden = state.status !== 'ready';
    link.removeAttribute('href');
    if (state.download_url) link.href = state.download_url;
  }
  const controller = createPhotoDownload({ onChange: paint, request: async (url, body) => {
    const response = await fetch(url, { method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) });
    if (!response.ok) throw new Error('order_unavailable');
    return response.json();
  }});
  summary.addEventListener('photo-selection-change', event => { selection = event.detail; controller.select(selection); });
  summary.addEventListener('photo-selection-download', event => { selection = event.detail; void controller.start(selection); });
  retry.addEventListener('click', () => { if (selection) void controller.start(selection); });
  link.addEventListener('click', async event => {
    event.preventDefault();
    if (link.getAttribute('aria-disabled') === 'true') return;
    const revision = deliveryRevision, url = link.href;
    link.setAttribute('aria-disabled', 'true');
    try {
      const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', referrerPolicy: 'no-referrer' });
      if (!response.ok) throw new Error('archive_unavailable');
      const blob = await response.blob();
      if (revision !== deliveryRevision) return;
      const blobUrl = URL.createObjectURL(blob), download = document.createElement('a');
      download.href = blobUrl; download.download = 'face-moment-photos.zip'; download.click();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    } catch { if (revision === deliveryRevision) paint({ status: 'failed' }); }
    finally { link.removeAttribute('aria-disabled'); }
  });
}

const summary = typeof document === 'undefined' ? null : document.querySelector('#photo-selection-summary');
const panel = typeof document === 'undefined' ? null : document.querySelector('#photo-download-panel');
if (summary && panel) mountPhotoDownload(summary, panel);
