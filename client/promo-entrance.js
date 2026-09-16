/** One-shot paper-card entrance, preserving the operator's saved geometry. */
const PHOTO_STAGGER_MS = 540;
const PHOTO_TRAVEL_MS = 2700;

export function animatePromoEntrance(card) {
  if (globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
  const photos = [...card.querySelectorAll('.promo-photo-card')];
  const qr = card.querySelector('.promo-qr-panel');
  const text = card.querySelector('.promo-copy h2');
  if (!qr?.animate) return;
  card.classList.add('has-paper-entrance');
  const width = window.innerWidth, height = window.innerHeight;

  function place(element, direction, delay, rotation, duration = 900) {
    const rect = element.getBoundingClientRect();
    const margin = Math.max(width, height) * .1;
    const x = direction.includes('left') ? -rect.right - margin
      : direction.includes('right') ? width - rect.left + margin : 0;
    const y = direction.includes('top') ? -rect.bottom - margin
      : direction.includes('bottom') ? height - rect.top + margin : 0;
    const restingShadow = getComputedStyle(element).boxShadow;
    const animation = element.animate([
      { offset: 0, translate: `${x}px ${y}px`, rotate: `${rotation}deg`, scale: '1.12',
        boxShadow: '0 5vmin 9vmin #0008' },
      { offset: .78, translate: '0px -8px', rotate: `${rotation * .08}deg`, scale: '1.015',
        boxShadow: '0 2vmin 4vmin #0006' },
      { offset: 1, translate: '0px 0px', rotate: '0deg', scale: '1', boxShadow: restingShadow },
    ], { duration, delay, easing: 'cubic-bezier(.16, 1, .3, 1)', fill: 'both' });
    void animation.finished.then(() => animation.cancel()).catch(() => {});
    return animation;
  }

  const directions = ['left', 'top', 'left bottom', 'bottom'];
  const rotations = [-14, 12, 10, -9];
  photos.forEach((photo, index) => place(
    photo,
    directions[index],
    index * PHOTO_STAGGER_MS,
    rotations[index],
    PHOTO_TRAVEL_MS,
  ));
  const photosSettled = Math.max(0, photos.length - 1) * PHOTO_STAGGER_MS + PHOTO_TRAVEL_MS;
  const qrAnimation = place(qr, 'right', photosSettled, 11);
  const qrSettled = photosSettled + 900;

  if (text) {
    const animation = text.animate([
      { offset: 0, opacity: 0, translate: '0px -5vh', rotate: '-8deg', scale: '1.24' },
      { offset: .28, opacity: 1, translate: '0px -3vh', rotate: '-5deg', scale: '1.16' },
      { offset: .84, opacity: 1, translate: '0px 0px', rotate: '0deg', scale: '.99' },
      { offset: 1, opacity: 1, translate: '0px 0px', rotate: '0deg', scale: '1' },
    ], { duration: 6000, delay: qrSettled + 1000,
      easing: 'linear', fill: 'both' });
    void animation.finished.then(() => animation.cancel()).catch(() => {});
  }
  // The issued QR becomes scan-ready only after its entrance has settled.
  return qrAnimation.finished.catch(() => {});
}
