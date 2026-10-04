import { mountPhotoSelection } from './public-photo-selection.js';
import { renderPublicPhotoGallery } from './public-photo-gallery.js';

// Browser adapts the accepted public API; profile and search decisions stay server-owned.
export async function searchCurrentSelfie(selfie, venueIds, confirmReset = false) {
  if (!(selfie instanceof Blob) || selfie.type !== 'image/jpeg' || venueIds.length < 1 || venueIds.length > 3 || new Set(venueIds).size !== venueIds.length) {
    throw new Error('invalid_search_input');
  }
  const body = new FormData();
  body.append('selfie', selfie, 'selfie.jpg');
  body.append('venue_ids', JSON.stringify(venueIds));
  if (confirmReset) body.append('confirm_reset', 'true');
  const response = await fetch('/api/public/search', { method: 'POST', credentials: 'same-origin', cache: 'no-store', body });
  if (!response.ok) throw new Error(response.status === 429 ? 'rate_limited' : 'request_failed');
  return response.json();
}

export function mountPublicPhotoSearch({ getCurrentSelfie }) {
  const venues = document.querySelector('#search-venues');
  const venueStatus = document.querySelector('#search-venue-status');
  const reload = document.querySelector('#search-venues-retry');
  const send = document.querySelector('#selfie-send');
  const retake = document.querySelector('#selfie-retake');
  const status = document.querySelector('#search-status');
  const progress = document.querySelector('#search-progress');
  const overlay = document.querySelector('#selfie-search-overlay');
  const confirmation = document.querySelector('#search-confirmation');
  const confirm = document.querySelector('#search-confirm');
  const summary = document.querySelector('#search-summary');
  const gallery = document.querySelector('#search-gallery');
  const selection = mountPhotoSelection(document.querySelector('#photo-selection-summary'));
  let busy = false, capture = null, pendingConfirmation = null;
  const inputs = () => [...venues.querySelectorAll('input')];
  const selected = () => inputs().filter(input => input.checked).map(input => input.value);
  function updateControls() {
    const count = selected().length;
    send.disabled = busy || !getCurrentSelfie() || count < 1 || count > 3;
    retake.disabled = busy;
    reload.disabled = busy;
    for (const input of inputs()) input.disabled = busy || (count === 3 && !input.checked);
    confirm.disabled = busy || !pendingConfirmation;
    progress.hidden = !busy; overlay.hidden = !busy;
  }
  function clearResult() {
    selection.clear();
    pendingConfirmation = null; confirmation.hidden = true;
    summary.replaceChildren(); summary.hidden = true; gallery.replaceChildren(); gallery.hidden = true; status.textContent = '';
  }
  function refreshCapture() {
    if (capture !== getCurrentSelfie()) { capture = getCurrentSelfie(); clearResult(); }
    updateControls();
  }
  async function loadVenues() {
    reload.hidden = true; venueStatus.textContent = 'Загружаем площадки…';
    try {
      const response = await fetch('/api/public/venues', { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error('venues_unavailable');
      const listing = await response.json();
      if (listing.schema_version !== 1 || !Array.isArray(listing.venues)) throw new Error('invalid_venues');
      venues.replaceChildren();
      for (const venue of listing.venues) {
        const label = document.createElement('label');
        const input = document.createElement('input'); input.type = 'checkbox'; input.value = venue.id;
        label.append(input, document.createTextNode(venue.name)); venues.append(label);
      }
      venueStatus.textContent = listing.venues.length ? 'Выберите от 1 до 3 площадок. Селфи отправится только после «Найти меня».' : 'Пока нет доступных площадок. Попробуйте позже.';
      reload.hidden = listing.venues.length > 0;
    } catch {
      venueStatus.textContent = 'Не удалось загрузить площадки. Проверьте соединение и повторите.'; reload.hidden = false;
    }
    updateControls();
  }
  function renderSummary(result) {
    const count = document.createElement('p'); count.textContent = `Ваших фотографий: ${result.personal_count}`;
    summary.append(count);
    for (const venue of result.venues) {
      if (!venue.personal.length) continue;
      const line = document.createElement('p');
      line.textContent = `${venue.name} — ${venue.personal.length} фото · ${venue.dates.join(', ')}`;
      summary.append(line);
    }
    summary.hidden = false;
  }
  async function submit(confirmReset = false) {
    if (busy || send.disabled || (confirmReset && pendingConfirmation !== getCurrentSelfie())) return;
    const selfie = getCurrentSelfie(), venueIds = selected();
    clearResult(); busy = true; updateControls();
    status.textContent = 'Ищем ваши моменты в выбранных площадках…';
    try {
      const result = await searchCurrentSelfie(selfie, venueIds, confirmReset);
      if (getCurrentSelfie() !== selfie) return;
      if (result.schema_version !== 1) throw new Error('invalid_response');
      switch (result.outcome) {
        case 'result':
          if (!Number.isInteger(result.personal_count) || result.personal_count < 1 || !Array.isArray(result.venues)) throw new Error('invalid_result');
          renderSummary(result); renderPublicPhotoGallery(gallery, result, selection.start(result)); status.textContent = 'Поиск завершён.'; break;
        case 'confirmation_required':
          pendingConfirmation = selfie; confirmation.hidden = false;
          status.textContent = result.message || 'Снимок отличается от предыдущих. Возможно, это другое лицо.'; break;
        case 'face_denied': status.textContent = result.message || 'Это лицо невозможно искать, так как оно отличается от тех лиц, которые вы искали ранее'; break;
        case 'retake_required': status.textContent = 'Переснимите селфи: нужно одно хорошо видимое лицо, занимающее не меньше трети кадра.'; break;
        case 'no_matches': status.textContent = 'Ваши фотографии не найдены в выбранных площадках. Попробуйте другое селфи или площадки.'; break;
        case 'busy': status.textContent = 'Поиск сейчас занят. Повторите через некоторое время.'; break;
        case 'deadline': status.textContent = 'Время поиска истекло. Попробуйте ещё раз.'; break;
        default: throw new Error('unknown_outcome');
      }
    } catch (error) {
      clearResult();
      status.textContent = error.message === 'rate_limited' ? 'Слишком много запросов. Подождите немного и повторите.' : 'Не удалось выполнить поиск. Проверьте соединение и попробуйте ещё раз.';
    } finally { busy = false; updateControls(); }
  }
  venues.addEventListener('change', () => { clearResult(); updateControls(); });
  send.addEventListener('click', () => void submit());
  confirm.addEventListener('click', () => void submit(true));
  reload.addEventListener('click', () => void loadVenues());
  void loadVenues();
  return { refreshCapture };
}
