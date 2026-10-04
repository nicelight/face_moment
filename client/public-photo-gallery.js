// Present only the server-granted current result; search scope and free flags stay server-owned.
export function renderPublicPhotoGallery(container, result, selection = null) {
  container.replaceChildren();
  let previews = Promise.resolve();
  for (const venue of result.venues) {
    const section = document.createElement('section');
    const heading = document.createElement('h2'); heading.textContent = venue.name; section.append(heading);
    const group = venue.personal.length ? selection?.venue(section) : null;
    if (!venue.personal.length) {
      const empty = document.createElement('p'); empty.textContent = 'Личные фотографии не найдены.'; section.append(empty);
    } else {
      for (const [title, photos, personal] of [['Ваши фотографии', venue.personal, true], ['Общие фотографии · бесплатно', venue.common, false]]) {
        if (!photos.length) continue;
        const subheading = document.createElement('h3'); subheading.textContent = title; section.append(subheading);
        const grid = document.createElement('div'); grid.className = 'fm-photo-grid';
        for (const photo of photos) {
          const figure = document.createElement('figure'); figure.dataset.photoId = photo.id;
          const frame = document.createElement('div'); frame.className = 'fm-photo-frame';
          const image = document.createElement('img'); image.alt = `${personal ? 'Личная' : 'Общая'} фотография · ${venue.name} · ${photo.visit_date}`;
          image.referrerPolicy = 'no-referrer'; frame.append(image);
          if (personal) { const watermark = document.createElement('span'); watermark.className = 'fm-photo-watermark'; watermark.textContent = 'face moment'; watermark.setAttribute('aria-hidden', 'true'); frame.append(watermark); }
          const caption = document.createElement('figcaption'); caption.textContent = `${photo.visit_date}${photo.is_free ? ' · Бесплатно' : ''}`;
          figure.append(frame, caption); grid.append(figure);
          const unavailable = selection?.photo(figure, photo, group);
          // The accepted backend has one preview renderer. Load in order, without a burst of busy requests.
          previews = previews.then(() => new Promise(resolve => {
            if (!container.contains(image)) { resolve(); return; }
            let retried = false;
            image.onload = resolve;
            image.onerror = () => {
              if (!container.contains(image)) { resolve(); return; }
              if (!retried && container.contains(image)) { retried = true; setTimeout(() => { image.src = photo.preview_url; }, 150); }
              else { caption.textContent += ' · Фото недоступно'; unavailable?.(); resolve(); }
            };
            image.src = photo.preview_url;
          }));
        }
        section.append(grid);
      }
    }
    container.append(section);
  }
  selection?.complete();
  container.hidden = false;
}
