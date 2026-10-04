const names = ['base_kopecks', 'd1', 'd2', 'd3'];
const url = '/api/serving/photo-tariff';

export async function mountPhotoTariff(form) {
  const inputs = names.map(name => form.elements.namedItem(name));
  const button = form.querySelector('button[type="submit"]');
  const status = form.querySelector('[role="status"]');
  const busy = value => { for (const input of inputs) input.disabled = value; button.disabled = value; };
  const render = values => names.forEach((name, index) => { inputs[index].value = String(values[name]); });
  const message = code => ({
    401: 'Войдите в аккаунт заново.',
    403: 'Нет прав на сохранение тарифа. Обновите страницу и повторите.',
    422: 'Тариф отклонён сервером. Проверьте Base и коэффициенты; сохранённый тариф не изменён.',
  })[code] || 'Не удалось сохранить тариф. Проверьте соединение и повторите.';
  busy(true);
  try {
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store' });
    if (response.ok) {
      render(await response.json()); status.textContent = '';
      busy(false);
    } else if (response.status === 503) {
      status.textContent = 'Тариф ещё не задан. Укажите Base и все коэффициенты.';
      busy(false);
    } else {
      status.textContent = 'Не удалось загрузить тариф. Проверьте права доступа и обновите страницу.';
    }
  } catch {
    status.textContent = 'Не удалось загрузить тариф. Проверьте соединение и обновите страницу.';
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (button.disabled) return;
    const [base, d1, d2, d3] = inputs.map(input => Number(input.value));
    if (inputs.some(input => !input.value.trim()) || !Number.isSafeInteger(base) || base <= 0 ||
        ![d1, d2, d3].every(Number.isFinite) || !(1 >= d1 && d1 >= d2 && d2 >= d3 && d3 > 0)) {
      status.textContent = 'Введите Base в целых копейках > 0 и коэффициенты: 1 ≥ d1 ≥ d2 ≥ d3 > 0.';
      return;
    }
    busy(true); status.textContent = 'Сохранение…';
    try {
      const csrf = document.cookie.split(';').map(value => value.trim())
        .find(value => value.startsWith('fm_staff_csrf='))?.slice('fm_staff_csrf='.length) ?? '';
      const response = await fetch(url, { method: 'PUT', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': decodeURIComponent(csrf) },
        body: JSON.stringify({ base_kopecks: base, d1: inputs[1].value, d2: inputs[2].value, d3: inputs[3].value }),
      });
      if (!response.ok) { status.textContent = message(response.status); return; }
      render(await response.json());
      status.textContent = 'Тариф сохранён.';
    } catch {
      status.textContent = 'Не удалось сохранить тариф. Проверьте соединение и повторите.';
    } finally { busy(false); }
  });
}

for (const form of document.querySelectorAll('[data-photo-tariff]')) void mountPhotoTariff(form);
