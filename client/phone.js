const SESSION_PATH = "/api/phone/session";
const ACTIVITY_PATH = "/api/phone/activity";
const SHELL_PATH = "/phone";

export function createPhoneController({
  documentRef,
  fetchImpl,
  locationRef,
  performanceRef,
  setTimeoutImpl,
  clearTimeoutImpl,
}) {
  const elements = {
    root: documentRef.getElementById("phone-session"),
    spa: documentRef.getElementById("phone-spa"),
    date: documentRef.getElementById("phone-date"),
    teaserFrame: documentRef.getElementById("phone-teaser-frame"),
    teaser: documentRef.getElementById("phone-teaser"),
    count: documentRef.getElementById("phone-count"),
    purchase: documentRef.getElementById("phone-purchase"),
    loading: documentRef.getElementById("phone-loading"),
  };

  let purchaseUrl = null;
  let expiryTimer = null;
  let failedMediaUrl = null;
  let mediaRecoveryUsed = false;

  function mediaUrlIdentity(value) {
    if (!value) return null;
    try {
      return new URL(value, documentRef.baseURI).href;
    } catch {
      return value;
    }
  }

  function clearPersonalizedState() {
    if (expiryTimer !== null) {
      clearTimeoutImpl(expiryTimer);
      expiryTimer = null;
    }
    purchaseUrl = null;
    failedMediaUrl = null;
    mediaRecoveryUsed = false;
    elements.root.hidden = true;
    delete elements.root.dataset.sessionId;
    elements.spa.textContent = "";
    elements.date.textContent = "";
    elements.count.textContent = "";
    elements.teaser.removeAttribute("src");
    elements.teaser.alt = "";
    elements.teaserFrame.hidden = true;
    elements.purchase.setAttribute("href", "#");
  }

  function leavePersonalizedView(target) {
    clearPersonalizedState();
    locationRef.replace(target);
  }

  function scheduleExpiry(idleExpiresInMs) {
    if (expiryTimer !== null) {
      clearTimeoutImpl(expiryTimer);
    }
    const duration = Math.max(0, Number(idleExpiresInMs));
    const deadline = performanceRef.now() + duration;
    const revalidateAtDeadline = async () => {
      const remaining = Math.max(0, deadline - performanceRef.now());
      if (remaining > 0) {
        expiryTimer = setTimeoutImpl(revalidateAtDeadline, remaining);
        return;
      }
      await loadSession(purchaseUrl || SHELL_PATH);
    };
    expiryTimer = setTimeoutImpl(revalidateAtDeadline, duration);
  }

  function renderSession(session) {
    purchaseUrl = session.purchase_url;
    elements.root.dataset.sessionId = session.session_id;
    elements.spa.textContent = session.spa_name;
    elements.date.textContent = session.visit_date;
    elements.count.textContent = String(session.n);
    elements.purchase.setAttribute("href", purchaseUrl);
    const teaserMediaUrl = session.teaser?.media_url || null;
    const teaserMediaIdentity = mediaUrlIdentity(teaserMediaUrl);
    if (teaserMediaUrl === null || teaserMediaIdentity === failedMediaUrl) {
      elements.teaser.removeAttribute("src");
      elements.teaser.alt = "";
      elements.teaserFrame.hidden = true;
    } else {
      elements.teaser.src = teaserMediaUrl;
      elements.teaser.alt = "Ваша фотография";
      elements.teaserFrame.hidden = false;
    }
    elements.loading.hidden = true;
    elements.root.hidden = false;
    scheduleExpiry(session.idle_expires_in_ms);
  }

  async function loadSession(failureTarget = SHELL_PATH) {
    try {
      const response = await fetchImpl(SESSION_PATH, {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        referrerPolicy: "no-referrer",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        leavePersonalizedView(failureTarget);
        return false;
      }
      renderSession(await response.json());
      return true;
    } catch {
      leavePersonalizedView(failureTarget);
      return false;
    }
  }

  async function recordActivity() {
    try {
      const response = await fetchImpl(ACTIVITY_PATH, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        referrerPolicy: "no-referrer",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ schema_version: 1 }),
      });
      if (!response.ok) {
        leavePersonalizedView(purchaseUrl || SHELL_PATH);
        return false;
      }
      const activity = await response.json();
      scheduleExpiry(activity.idle_expires_in_ms);
      return true;
    } catch {
      leavePersonalizedView(purchaseUrl || SHELL_PATH);
      return false;
    }
  }

  async function handlePurchase(event) {
    event.preventDefault();
    const target = purchaseUrl;
    if (target === null || !(await recordActivity())) {
      return;
    }
    clearPersonalizedState();
    locationRef.assign(target);
  }

  async function handleTeaserError() {
    failedMediaUrl = mediaUrlIdentity(elements.teaser.src) || failedMediaUrl;
    elements.teaser.removeAttribute("src");
    elements.teaser.alt = "";
    elements.teaserFrame.hidden = true;
    if (mediaRecoveryUsed) {
      return;
    }
    mediaRecoveryUsed = true;
    await loadSession();
  }

  elements.purchase.addEventListener("click", handlePurchase);
  elements.teaser.addEventListener("error", handleTeaserError);

  return {
    clearPersonalizedState,
    loadSession,
    recordActivity,
  };
}

if (typeof document !== "undefined") {
  const controller = createPhoneController({
    documentRef: document,
    fetchImpl: globalThis.fetch.bind(globalThis),
    locationRef: globalThis.location,
    performanceRef: globalThis.performance,
    setTimeoutImpl: globalThis.setTimeout.bind(globalThis),
    clearTimeoutImpl: globalThis.clearTimeout.bind(globalThis),
  });
  void controller.loadSession();
}
