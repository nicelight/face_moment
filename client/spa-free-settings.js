export function confirmFreeMode(isFree, wasFree = false) {
  return !isFree || wasFree || window.confirm('Сделать фотографии площадки бесплатными? Посетители смогут скачать их без оплаты.');
}

export function mountSpaFreeMode(form) {
  const input = form.elements.namedItem('is_free');
  const button = form.querySelector('button[type="submit"]');
  const status = form.querySelector('[role="status"]');
  let saved = form.dataset.isFree === 'true';
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (button.disabled || !confirmFreeMode(input.checked, saved)) return;
    const isFree = input.checked;
    button.disabled = input.disabled = true;
    status.textContent = 'Сохранение…';
    try {
      const csrf = document.cookie.split(';').map(value => value.trim())
        .find(value => value.startsWith('fm_staff_csrf='))?.slice('fm_staff_csrf='.length) ?? '';
      const response = await fetch(`/api/serving/spas/${encodeURIComponent(form.dataset.spaId)}/is-free`, {
        method:'PUT', credentials:'same-origin', cache:'no-store',
        headers:{'Content-Type':'application/json','X-CSRF-Token':decodeURIComponent(csrf)},
        body:JSON.stringify({is_free:isFree}),
      });
      if (!response.ok) {
        status.textContent = ({401:'Войдите в аккаунт заново.',403:'Нет прав на изменение режима. Обновите страницу.',
          404:'Площадка не найдена.',422:'Режим отклонён сервером.'})[response.status] || 'Не удалось сохранить режим. Обновите страницу.';
        return;
      }
      saved = (await response.json()).is_free;
      input.checked = saved;
      form.dataset.isFree = String(saved);
      status.textContent = 'Режим сохранён.';
    } catch {
      status.textContent = 'Соединение прервано. Обновите страницу перед повторной попыткой.';
    } finally {
      button.disabled = input.disabled = false;
    }
  });
}
for (const form of document.querySelectorAll('[data-spa-free]')) mountSpaFreeMode(form);
