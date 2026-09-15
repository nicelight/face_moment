import { readDisplayClientToken } from './display-client-config.js';
import { readAdvertisingCaption } from './advertising-caption.js';

/** A single playlist, two visual layers and an explicit browser media cache. */
export function createAdvertisingPlayer({ onReady = () => {} } = {}) {
  const layer = document.createElement('div');
  layer.className = 'ad-player';
  layer.hidden = true;
  layer.setAttribute('aria-hidden', 'true');
  document.body.prepend(layer);
  const caption = document.createElement('div');
  caption.className = 'advertising-caption';
  document.body.append(caption);
  let playlist = null, pending = null;
  let token = null, cache = null;
  let identity = 0, generation = 0, running = false;
  let index = -1, current = null, timer = null;
  let refreshing = false, warming = false;
  const downloads = new Map();

  function dispose(element) {
    if (!element) return;
    if (element.tagName === 'VIDEO') {
      element.pause();
      element.removeAttribute('src');
      element.load();
    }
    if (element.dataset.blobUrl) URL.revokeObjectURL(element.dataset.blobUrl);
    element.remove();
  }

  function stop() {
    running = false;
    generation += 1;
    clearTimeout(timer);
    timer = null;
    [...layer.children].forEach(dispose);
    current = null;
    layer.hidden = true;
    delete document.body.dataset.adPlaying;
  }

  async function fetchAsset(item, expectedIdentity) {
    const storage = cache;
    const credential = token;
    const cached = await storage?.match(item.url);
    if (cached) return cached;
    if (expectedIdentity !== identity) throw new Error('advertising_identity_changed');
    if (!downloads.has(item.url)) {
      const download = (async () => {
        const response = await fetch(item.url, { headers: { Authorization: `Bearer ${credential}` },
          cache: 'no-store', signal: AbortSignal.timeout(120000) });
        if (!response.ok) throw new Error(`advertising_media_http_${response.status}`);
        // Buffer to a Blob so both playback and explicit cache get complete bytes.
        const blob = await response.blob();
        const complete = new Response(blob, { headers: { 'Content-Type': item.content_type } });
        if (expectedIdentity !== identity) throw new Error('advertising_identity_changed');
        try { await storage?.put(item.url, complete.clone()); }
        catch (error) { console.warn('Реклама: не удалось сохранить материал в кэш браузера.', error); }
        return complete;
      })();
      downloads.set(item.url, download);
      void download.finally(() => { if (downloads.get(item.url) === download) downloads.delete(item.url); }).catch(() => {});
    }
    return (await downloads.get(item.url)).clone();
  }

  async function warm(expectedIdentity) {
    if (warming || !cache) return;
    warming = true;
    try {
      const snapshot = pending ?? playlist;
      if (!snapshot) return;
      for (const item of snapshot.items) {
        if (expectedIdentity !== identity) return;
        try { await fetchAsset(item, expectedIdentity); } catch { /* Retry on later polling; available assets keep playing. */ }
      }
      // Prune only this credential's advertising cache, preserving the latest list.
      if (expectedIdentity !== identity) return;
      const urls = new Set((pending ?? playlist)?.items.map(item => new URL(item.url, location.origin).href));
      for (const request of await cache.keys()) {
        if (!urls.has(request.url)) await cache.delete(request);
      }
    } finally { warming = false; }
  }

  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    try {
      const credential = readDisplayClientToken();
      if (credential !== token) {
        const wasRunning = running;
        stop();
        token = credential;
        identity += 1;
        downloads.clear();
        playlist = pending = null;
        cache = null;
        running = wasRunning;
        if (credential) {
          const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(credential));
          const key = [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
          try { cache = await caches.open(`face-moment-advertising-${key}`); }
          catch (error) { console.warn('Реклама: Cache Storage недоступен.', error); }
        }
      }
      if (!credential) return;
      const expectedIdentity = identity;
      const response = await fetch('/api/promo/advertising/playlist', {
        headers: { Authorization: `Bearer ${credential}` }, cache: 'no-store', signal: AbortSignal.timeout(10000),
      });
      if (!response.ok) throw new Error(`advertising_playlist_http_${response.status}`);
      const next = await response.json();
      if (expectedIdentity !== identity) return;
      if (!playlist) {
        playlist = next;
        if (running && !current) restart();
      } else if (next.revision !== (pending ?? playlist).revision || next.spa_id !== playlist.spa_id) {
        pending = next;
        if (running && !current) restart();
      }
      void warm(expectedIdentity);
    } catch { /* A loaded display keeps its in-memory playlist and cached media. */ }
    finally { refreshing = false; }
  }

  function applyPending() {
    if (!pending) return;
    const currentId = playlist?.items[index]?.id;
    playlist = pending;
    pending = null;
    index = playlist.items.findIndex(item => item.id === currentId);
  }

  async function prepare(item, expectedIdentity) {
    const blob = await (await fetchAsset(item, expectedIdentity)).blob();
    const element = document.createElement(item.content_type === 'video/webm' ? 'video' : 'img');
    const url = URL.createObjectURL(blob);
    element.dataset.blobUrl = url;
    if (element.tagName === 'VIDEO') {
      element.playsInline = true;
      element.preload = 'auto';
    } else element.alt = '';
    try {
      await new Promise((resolve, reject) => {
        const readyEvent = element.tagName === 'VIDEO' ? 'loadeddata' : 'load';
        const timeout = setTimeout(() => finish(new Error('advertising_media_load_timeout')), 15000);
        const ready = () => finish();
        const failed = () => finish(new Error('advertising_media_decode_failed'));
        function finish(error) {
          clearTimeout(timeout);
          element.removeEventListener(readyEvent, ready);
          element.removeEventListener('error', failed);
          error ? reject(error) : resolve();
        }
        element.addEventListener(readyEvent, ready);
        element.addEventListener('error', failed);
        element.src = url;
      });
      return element;
    } catch (error) { dispose(element); throw error; }
  }

  async function advance(expectedGeneration, failedCount = 0) {
    if (!running || generation !== expectedGeneration) return;
    clearTimeout(timer);
    applyPending();
    if (!playlist?.items.length) {
      [...layer.children].forEach(dispose);
      current = null;
      layer.hidden = true;
      delete document.body.dataset.adPlaying;
      if (playlist) onReady();
      return;
    }
    if (failedCount >= playlist.items.length) {
      [...layer.children].forEach(dispose);
      current = null;
      layer.hidden = true;
      delete document.body.dataset.adPlaying;
      onReady();
      timer = setTimeout(() => advance(expectedGeneration), 30000);
      return;
    }
    index = (index + 1) % playlist.items.length;
    const item = playlist.items[index];
    let incoming;
    try { incoming = await prepare(item, identity); }
    catch {
      if (running && generation === expectedGeneration) void advance(expectedGeneration, failedCount + 1);
      return;
    }
    if (!running || generation !== expectedGeneration) { dispose(incoming); return; }
    const outgoing = current;
    if (outgoing?.tagName === 'VIDEO') outgoing.pause();
    const fade = outgoing ? Math.min(playlist.crossfade_seconds, playlist.image_seconds) * 1000 : 0;
    incoming.style.transition = fade ? `opacity ${fade}ms linear` : 'none';
    layer.append(incoming);
    layer.hidden = false;
    document.body.dataset.adPlaying = '';
    current = incoming;
    // Establish opacity zero before revealing the next visual layer.
    void incoming.offsetWidth;
    incoming.style.opacity = '1';
    if (!outgoing) onReady();
    if (outgoing) {
      if (fade) setTimeout(() => dispose(outgoing), fade);
      else dispose(outgoing);
    }
    let advanced = false;
    const next = () => {
      if (advanced || !running || generation !== expectedGeneration || current !== incoming) return;
      advanced = true;
      if (incoming.tagName === 'VIDEO') incoming.pause();
      void advance(expectedGeneration);
    };
    incoming.addEventListener('error', next, { once: true });
    if (incoming.tagName === 'VIDEO') {
      incoming.addEventListener('ended', next, { once: true });
      try { await incoming.play(); }
      catch (error) {
        if (error.name === 'NotAllowedError' && running && generation === expectedGeneration) {
          // Until kiosk autoplay policy is configured, continue visuals without sound.
          incoming.muted = true;
          try { await incoming.play(); } catch { next(); }
        } else next();
      }
    } else {
      timer = setTimeout(next, playlist.image_seconds * 1000);
    }
  }

  function restart() {
    stop();
    running = true;
    applyPending();
    index = playlist?.random_start && playlist.items.length
      ? Math.floor(Math.random() * playlist.items.length) - 1 : -1;
    void advance(generation);
  }

  function start() {
    const settings = readAdvertisingCaption();
    caption.textContent = settings.text;
    caption.style.fontSize = `${settings.size}px`;
    if (!running) restart();
    void refresh();
  }

  const poll = setInterval(() => void refresh(), 30000);
  window.addEventListener('pagehide', () => { clearInterval(poll); stop(); });
  return { start, stop, refresh };
}
