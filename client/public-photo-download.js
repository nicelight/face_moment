// Browser consumes the selected quote and promo order API; the server owns price and delivery.
export function createPhotoDownload({ request, makeId = () => crypto.randomUUID(), onChange = () => {},
  navigate = url => window.location.assign(url), remember = () => {}, forget = () => {} }) {
  let attempt = null;
  let blockedKey = null;
  const emit = state => onChange(Number.isInteger(attempt?.total_kopecks)
    ? {...state, total_kopecks: attempt.total_kopecks} : state);
  const key = selection => JSON.stringify([selection.result_id, [...selection.photo_ids].sort()]);
  function select(selection) {
    if (attempt?.redirected && !selection.photo_ids.length) return;
    const nextKey = key(selection);
    if (blockedKey && blockedKey !== nextKey) { blockedKey = null; emit({ status: 'idle' }); }
    if (attempt && attempt.key !== nextKey) { attempt = null; forget(); emit({ status: 'idle' }); }
  }
  async function start(selection, payment = null) {
    select(selection);
    if (blockedKey === key(selection)) return;
    if (!selection.quote || !selection.photo_ids.length) return;
    const paid = selection.quote.total_kopecks > 0 && selection.quote.paid_count > 0;
    if (!paid && (selection.quote.total_kopecks !== 0 || selection.quote.paid_count !== 0)) return;
    if (paid && !payment && !attempt) { emit({status:'email'}); return; }
    if (!attempt) attempt = { key: key(selection), body: { result_id: selection.result_id,
      photo_ids: [...selection.photo_ids], client_request_id: makeId(),
      ...(paid ? {email: payment.email, payment_method: payment.payment_method} : {}) },
      order: null, paid, redirected: false, busy: false };
    const current = attempt;
    if (current.busy) return;
    current.busy = true;
    emit({ status: 'loading' });
    try {
      if (!current.order) current.order = await request('/api/public/orders', current.body);
      if (!Number.isInteger(current.order.total_kopecks) || current.order.total_kopecks < 0) throw new Error('invalid_order_total');
      current.total_kopecks = current.order.total_kopecks;
      current.paid = current.total_kopecks > 0;
      emit({ status: 'loading' });
      const order = await request(`/api/public/orders/${current.order.id}`);
      if (attempt !== current) return;
      if (order.total_kopecks !== current.total_kopecks) throw new Error('order_total_mismatch');
      if (order.archive_status === 'failed') emit({ status: 'failed' });
      else if (order.archive_status === 'ready' && order.download_url && (!current.paid || order.payment_status === 'succeeded')) {
        emit({ status: 'ready', download_url: order.download_url, paid: current.paid });
      }
      else if (order.archive_status === 'requested' || order.archive_status === 'preparing') emit({ status: 'preparing' });
      else if (current.paid && order.payment_status === 'canceled') emit({status:'canceled'});
      else if (current.paid && order.payment_status === 'succeeded') emit({status:'unavailable'});
      else if (current.paid && order.archive_status === 'ready' && current.redirected) emit({status:'pending'});
      else if (current.paid && order.archive_status === 'ready' && order.payment_status === 'pending') {
        const response = await request(`/api/public/orders/${current.order.id}/payment`, {});
        if (attempt !== current) return;
        const url = response.confirmation_url;
        if (typeof url !== 'string' || !url.startsWith('https://')) throw new Error('invalid_confirmation_url');
        current.redirected = true;
        remember({key:current.key, id:current.order.id, client_request_id:current.body.client_request_id});
        emit({status:'redirecting'});
        navigate(url);
      }
      else emit({ status: 'failed' });
    } catch (error) {
      if (attempt !== current) return;
      if (!current.order && !current.paid && error?.status === 422) {
        let changed = false;
        try {
          const quote = await request('/api/public/quote', {
            result_id: current.body.result_id, photo_ids: current.body.photo_ids });
          changed = quote.currency === 'RUB' && quote.selected_count === current.body.photo_ids.length
            && Number.isInteger(quote.total_kopecks) && quote.total_kopecks > 0
            && Number.isInteger(quote.paid_count) && quote.paid_count > 0;
        } catch { /* A failed quote cannot establish changed conditions. */ }
        if (attempt !== current) return;
        attempt = null;
        blockedKey = current.key;
        emit({ status: changed ? 'changed' : 'invalid' });
      } else emit({ status: 'error' });
    }
    finally { current.busy = false; }
  }
  async function resume(saved) {
    if (!saved || typeof saved.id !== 'string' || typeof saved.key !== 'string') return;
    attempt = {key:saved.key, body:{client_request_id:saved.client_request_id}, order:{id:saved.id}, paid:true, redirected:true, busy:false};
    emit({status:'loading'});
    try {
      const order = await request(`/api/public/orders/${saved.id}`);
      if (!Number.isInteger(order.total_kopecks) || order.total_kopecks <= 0) throw new Error('paid_order_required');
      attempt.total_kopecks = order.total_kopecks;
      attempt.order.total_kopecks = order.total_kopecks;
      if (order.archive_status === 'ready' && order.payment_status === 'succeeded' && order.download_url) emit({status:'ready',download_url:order.download_url,paid:true});
      else if (order.archive_status === 'failed') emit({status:'failed'});
      else if (order.payment_status === 'canceled') emit({status:'canceled'});
      else if (order.payment_status === 'succeeded') emit({status:'unavailable'});
      else if (order.archive_status === 'requested' || order.archive_status === 'preparing') emit({status:'preparing'});
      else emit({status:'pending'});
    } catch { emit({status:'error'}); }
  }
  return { select, start, resume, refresh: () => attempt?.order ? resume({key:attempt.key,id:attempt.order.id,client_request_id:attempt.body.client_request_id}) : undefined };
}

export function mountPhotoDownload(summary, panel) {
  const message = panel.querySelector('#photo-download-status');
  const retry = panel.querySelector('#photo-download-retry');
  const link = panel.querySelector('#photo-download-link');
  const form = panel.querySelector('#photo-payment-form');
  const selectionTotal = summary.querySelector('#photo-selection-total');
  let selection = null, deliveryRevision = 0, paidDelivery = false;
  function paint(state) {
    deliveryRevision++;
    paidDelivery = state.status === 'ready' && state.paid === true;
    panel.hidden = state.status === 'idle';
    if (selectionTotal && Number.isInteger(state.total_kopecks)) selectionTotal.textContent =
      `${new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(state.total_kopecks / 100)} ₽`;
    if (form) form.hidden = state.status !== 'email';
    message.textContent = ({ email: 'Укажите email и способ оплаты для выбранных фотографий.', loading: 'Проверяем архив…', preparing: 'Архив готовится. Повторите через 30 секунд.', failed: 'Не удалось подготовить архив. Обратитесь в поддержку.', canceled: 'Оплата не подтверждена. Обратитесь в поддержку, если нужна помощь.', pending: 'Ожидаем подтверждения оплаты. Проверьте снова через 30 секунд.', redirecting: 'Переходим к оплате…', unavailable: 'Архив недоступен или срок ссылки истёк. Обратитесь в поддержку для ручного возврата.', changed: 'Условия изменились, выберите фотографии повторно', invalid: 'Не удалось оформить заказ. Выберите фотографии повторно.', error: 'Не удалось проверить архив. Повторите попытку. Если ошибка сохраняется, обратитесь в поддержку.', ready: 'Архив готов. Скачайте выбранные фотографии.' })[state.status] || '';
    if (selectionTotal && ['changed', 'invalid'].includes(state.status)) selectionTotal.textContent = 'Выберите фотографии повторно';
    retry.hidden = !['preparing', 'pending', 'error', 'failed', 'canceled'].includes(state.status);
    retry.disabled = state.status === 'loading';
    link.hidden = state.status !== 'ready';
    link.removeAttribute('href');
    if (state.download_url) link.href = state.download_url;
  }
  const memoryKey = 'fm_paid_photo_order';
  const controller = createPhotoDownload({ onChange: paint,
    remember: value => sessionStorage.setItem(memoryKey, JSON.stringify(value)),
    forget: () => sessionStorage.removeItem(memoryKey),
    request: async (url, body) => {
    const response = await fetch(url, { method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) });
    if (!response.ok) throw Object.assign(new Error('order_unavailable'), {status: response.status});
    return response.json();
  }});
  summary.addEventListener('photo-selection-change', event => { selection = event.detail; controller.select(selection); });
  summary.addEventListener('photo-selection-download', event => { selection = event.detail; void controller.start(selection); });
  form?.addEventListener('submit', event => {
    event.preventDefault();
    if (!selection || !form.reportValidity()) return;
    const email = form.elements.namedItem('email').value.trim();
    const payment_method = form.elements.namedItem('payment_method').value;
    if (!['bank_card','sbp'].includes(payment_method)) return;
    void controller.start(selection, {email,payment_method});
  });
  retry.addEventListener('click', () => { if (selection?.photo_ids.length) void controller.start(selection); else void controller.refresh(); });
  try {
    const saved = JSON.parse(sessionStorage.getItem(memoryKey));
    if (saved) void controller.resume(saved);
  } catch { sessionStorage.removeItem(memoryKey); }
  link.addEventListener('click', async event => {
    event.preventDefault();
    if (link.getAttribute('aria-disabled') === 'true') return;
    const revision = deliveryRevision, url = link.href, paid = paidDelivery;
    link.setAttribute('aria-disabled', 'true');
    try {
      const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', referrerPolicy: 'no-referrer' });
      if (!response.ok) throw new Error('archive_unavailable');
      const blob = await response.blob();
      if (revision !== deliveryRevision) return;
      const blobUrl = URL.createObjectURL(blob), download = document.createElement('a');
      download.href = blobUrl; download.download = 'face-moment-photos.zip'; download.click();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    } catch { if (revision === deliveryRevision) paint({ status: paid ? 'unavailable' : 'failed' }); }
    finally { link.removeAttribute('aria-disabled'); }
  });
}

const summary = typeof document === 'undefined' ? null : document.querySelector('#photo-selection-summary');
const panel = typeof document === 'undefined' ? null : document.querySelector('#photo-download-panel');
if (summary && panel) mountPhotoDownload(summary, panel);
