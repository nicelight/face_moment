import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { createPhoneController } from "../../client/phone.js";


class FakeElement {
  constructor() {
    this.textContent = "";
    this.hidden = false;
    this.dataset = {};
    this.alt = "";
    this.src = "";
    this.attributes = new Map();
    this.listeners = new Map();
  }

  setAttribute(name, value) {
    this.attributes.set(name, value);
    if (name === "src") this.src = value;
  }

  removeAttribute(name) {
    this.attributes.delete(name);
    if (name === "src") this.src = "";
  }

  addEventListener(name, callback) {
    this.listeners.set(name, callback);
  }
}


function fixture() {
  const ids = [
    "phone-session",
    "phone-spa",
    "phone-date",
    "phone-teaser-frame",
    "phone-teaser",
    "phone-count",
    "phone-purchase",
    "phone-loading",
  ];
  const elements = Object.fromEntries(ids.map((id) => [id, new FakeElement()]));
  elements["phone-session"].hidden = true;
  elements["phone-teaser-frame"].hidden = true;

  const fetchCalls = [];
  const responses = [];
  const fetchImpl = async (...args) => {
    fetchCalls.push(args);
    return responses.shift();
  };
  const timers = [];
  const clearedTimers = [];
  const clock = { now: 0 };
  const navigation = { replacements: [], assignments: [] };
  const locationRef = {
    replace(target) {
      navigation.replacements.push({
        target,
        spa: elements["phone-spa"].textContent,
        count: elements["phone-count"].textContent,
        sessionId: elements["phone-session"].dataset.sessionId,
        teaser: elements["phone-teaser"].src,
      });
    },
    assign(target) {
      navigation.assignments.push(target);
    },
  };
  const controller = createPhoneController({
    documentRef: {
      baseURI: "https://central.example.test/phone",
      getElementById: (id) => elements[id],
    },
    fetchImpl,
    locationRef,
    performanceRef: { now: () => clock.now },
    setTimeoutImpl(callback, delay) {
      const token = { callback, delay };
      timers.push(token);
      return token;
    },
    clearTimeoutImpl(token) {
      clearedTimers.push(token);
    },
  });
  return {
    elements,
    fetchCalls,
    responses,
    timers,
    clearedTimers,
    clock,
    navigation,
    controller,
  };
}


function sessionResponse({ idleMs = 3_600_000, teaser = true } = {}) {
  return {
    ok: true,
    async json() {
      return {
        schema_version: 1,
        session_id: "aa39236f-17e3-41eb-9c22-75a49ef21f93",
        spa_name: "Pilot SPA",
        visit_date: "2026-08-28",
        teaser: teaser
          ? {
              photo_id: "2b22eb29-f8a3-4083-bc57-6776295effcb",
              media_url: "/api/phone/media/opaque-reference",
            }
          : null,
        n: 12,
        purchase_url: "https://face.example.test/purchase",
        idle_expires_at: "2026-08-28T09:00:00.000Z",
        idle_expires_in_ms: idleMs,
      };
    },
  };
}


test("passive protected read renders only in-memory session state", async () => {
  const state = fixture();
  state.responses.push(sessionResponse());

  assert.equal(await state.controller.loadSession(), true);
  assert.equal(state.fetchCalls.length, 1);
  assert.deepEqual(state.fetchCalls[0], [
    "/api/phone/session",
    {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      referrerPolicy: "no-referrer",
      headers: { Accept: "application/json" },
    },
  ]);
  assert.equal(state.elements["phone-session"].hidden, false);
  assert.equal(state.elements["phone-spa"].textContent, "Pilot SPA");
  assert.equal(state.elements["phone-date"].textContent, "2026-08-28");
  assert.equal(state.elements["phone-count"].textContent, "12");
  assert.equal(
    state.elements["phone-teaser"].src,
    "/api/phone/media/opaque-reference",
  );
  assert.equal(
    state.elements["phone-purchase"].attributes.get("href"),
    "https://face.example.test/purchase",
  );
  assert.equal(state.timers[0].delay, 3_600_000);
  assert.equal(state.fetchCalls.some(([path]) => path === "/api/phone/activity"), false);
});


test("local monotonic expiry clears every personalized field before replace", async () => {
  const state = fixture();
  state.responses.push(sessionResponse({ idleMs: 125 }));
  await state.controller.loadSession();
  state.responses.push({ ok: false });

  state.clock.now = 125;
  await state.timers[0].callback();

  assert.deepEqual(state.navigation.replacements, [
    {
      target: "https://face.example.test/purchase",
      spa: "",
      count: "",
      sessionId: undefined,
      teaser: "",
    },
  ]);
  assert.equal(state.elements["phone-session"].hidden, true);
  assert.equal(state.elements["phone-date"].textContent, "");
  assert.equal(state.elements["phone-purchase"].attributes.get("href"), "#");
});


test("a stale local deadline passively observes another phone's shared extension", async () => {
  const state = fixture();
  state.responses.push(sessionResponse({ idleMs: 125 }));
  await state.controller.loadSession();

  state.responses.push(sessionResponse({ idleMs: 3_600_000 }));
  state.clock.now = 125;
  await state.timers[0].callback();

  assert.equal(state.fetchCalls.length, 2);
  assert.equal(state.fetchCalls.every(([path]) => path === "/api/phone/session"), true);
  assert.equal(state.fetchCalls.some(([path]) => path === "/api/phone/activity"), false);
  assert.deepEqual(state.navigation.replacements, []);
  assert.equal(state.elements["phone-session"].hidden, false);
  assert.equal(state.timers.at(-1).delay, 3_600_000);
});


test("purchase click is the explicit activity operation and then navigates safely", async () => {
  const state = fixture();
  state.responses.push(sessionResponse({ idleMs: 1000 }));
  state.responses.push({
    ok: true,
    async json() {
      return {
        schema_version: 1,
        idle_expires_at: "2026-08-28T09:10:00.000Z",
        idle_expires_in_ms: 3_600_000,
      };
    },
  });
  await state.controller.loadSession();

  let prevented = false;
  await state.elements["phone-purchase"].listeners.get("click")({
    preventDefault() {
      prevented = true;
    },
  });

  assert.equal(prevented, true);
  assert.deepEqual(state.fetchCalls[1], [
    "/api/phone/activity",
    {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      referrerPolicy: "no-referrer",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ schema_version: 1 }),
    },
  ]);
  assert.equal(state.timers.at(-1).delay, 3_600_000);
  assert.deepEqual(state.navigation.assignments, [
    "https://face.example.test/purchase",
  ]);
  assert.equal(state.elements["phone-session"].hidden, true);
  assert.equal(state.elements["phone-count"].textContent, "");
});


test("rejected protected read clears state before the safe shell redirect", async () => {
  const state = fixture();
  state.elements["phone-spa"].textContent = "stale SPA";
  state.elements["phone-count"].textContent = "99";
  state.elements["phone-session"].dataset.sessionId = "stale-session";
  state.elements["phone-teaser"].src = "/stale.jpg";
  state.responses.push({ ok: false });

  assert.equal(await state.controller.loadSession(), false);
  assert.deepEqual(state.navigation.replacements, [
    {
      target: "/phone",
      spa: "",
      count: "",
      sessionId: undefined,
      teaser: "",
    },
  ]);
});


test("a disappeared teaser triggers one passive refresh without a retry loop", async () => {
  const state = fixture();
  state.responses.push(sessionResponse());
  state.responses.push(sessionResponse());
  await state.controller.loadSession();

  await state.elements["phone-teaser"].listeners.get("error")();

  assert.equal(state.fetchCalls.length, 2);
  assert.equal(state.fetchCalls.some(([path]) => path === "/api/phone/activity"), false);
  assert.equal(state.elements["phone-teaser"].src, "");
  assert.equal(state.elements["phone-teaser-frame"].hidden, true);
});


test("browser-normalized media identity permits at most one passive recovery", async () => {
  const state = fixture();
  state.responses.push(sessionResponse());
  state.responses.push(sessionResponse());
  await state.controller.loadSession();

  state.elements["phone-teaser"].src =
    "https://central.example.test/api/phone/media/opaque-reference";
  await state.elements["phone-teaser"].listeners.get("error")();
  await state.elements["phone-teaser"].listeners.get("error")();

  assert.equal(state.fetchCalls.length, 2);
  assert.equal(state.fetchCalls.every(([path]) => path === "/api/phone/session"), true);
  assert.equal(state.fetchCalls.some(([path]) => path === "/api/phone/activity"), false);
  assert.equal(state.elements["phone-teaser"].src, "");
  assert.equal(state.elements["phone-teaser-frame"].hidden, true);
});


test("phone bundle retains no durable state and declares no-referrer delivery", async () => {
  const source = await readFile(new URL("../../client/phone.js", import.meta.url), "utf8");
  const html = await readFile(new URL("../../client/phone.html", import.meta.url), "utf8");

  for (const forbidden of ["localStorage", "sessionStorage", "indexedDB", "caches.open"]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
  assert.match(source, /locationRef\.replace/);
  assert.match(source, /clearPersonalizedState\(\);\s*locationRef\.replace/s);
  assert.match(source, /cache: "no-store"/);
  assert.match(source, /referrerPolicy: "no-referrer"/);
  assert.match(html, /<meta name="referrer" content="no-referrer">/);
  assert.match(html, /rel="noreferrer"/);
  assert.doesNotMatch(html, /session_id|ticket|teaser_photo_ids/);
});
