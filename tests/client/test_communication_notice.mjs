import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  CommunicationNoticeController,
  COMMUNICATION_NOTICE_DURATION_MS,
  formatServerCommunicationNotice,
} from "../../client/communication-notice.js";

function fakeElement() {
  return { hidden: false, textContent: "" };
}

function fakeTimers() {
  const scheduled = [];
  const cleared = [];
  return {
    scheduled,
    cleared,
    setTimeoutImpl(callback, delay) {
      const timer = { callback, delay };
      scheduled.push(timer);
      return timer;
    },
    clearTimeoutImpl(timer) {
      cleared.push(timer);
    },
  };
}

const firstTime = new Date(2026, 7, 21, 10, 5, 6).getTime();
const secondTime = new Date(2026, 7, 21, 10, 5, 9).getTime();
assert.match(
  formatServerCommunicationNotice(firstTime),
  /^Попытка связи с сервером была не успешна в 10:05:06$/,
);

const element = fakeElement();
const timers = fakeTimers();
let now = firstTime;
const controller = new CommunicationNoticeController({
  element,
  clock: () => now,
  setTimeoutImpl: timers.setTimeoutImpl,
  clearTimeoutImpl: timers.clearTimeoutImpl,
});

const first = controller.show();
assert.equal(first.durationMs, COMMUNICATION_NOTICE_DURATION_MS);
assert.equal(first.durationMs >= 5_000 && first.durationMs <= 10_000, true);
assert.equal(element.hidden, false);
assert.equal(element.textContent, "Попытка связи с сервером была не успешна в 10:05:06");
assert.equal(timers.scheduled.at(-1).delay, COMMUNICATION_NOTICE_DURATION_MS);

const firstTimer = timers.scheduled.at(-1);
now = secondTime;
controller.show();
assert.equal(element.hidden, false);
assert.equal(element.textContent, "Попытка связи с сервером была не успешна в 10:05:09");
assert.ok(timers.cleared.includes(firstTimer));

firstTimer.callback();
assert.equal(element.hidden, false, "a replaced notice remains visible");
timers.scheduled.at(-1).callback();
assert.equal(element.hidden, true);
assert.equal(element.textContent, "");

const app = await readFile("client/app.js", "utf8");
const html = await readFile("client/index.html", "utf8");
const css = await readFile("client/styles.css", "utf8");
assert.match(app, /face-moment:attempt-transport-failure/);
assert.match(app, /communicationNoticeController\.show\(\)/);
assert.match(app, /"http_failure"/);
assert.match(app, /"typed_response_invalid"/);
assert.match(html, /id="communication-notice"/);
assert.match(css, /\.communication-notice[\s\S]*pointer-events: none/);

console.log(
  "communication notice GREEN: exact local time, 7-second bounded visibility, immediate replacement and non-blocking client wiring",
);
