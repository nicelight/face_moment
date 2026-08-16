#!/usr/bin/env node

const cdpBase = process.env.KIOSK_CDP_URL ?? "http://127.0.0.1:9222";
const listedOrigin = process.env.FACE_MOMENT_ORIGIN ?? "https://localhost:8443";
const unlistedOrigin =
  process.env.FACE_MOMENT_UNLISTED_ORIGIN ?? "https://localhost:9443";
const permissionNames = [
  "local-network",
  "loopback-network",
  "local-network-access",
];

const sleep = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

const pages = await fetch(`${cdpBase}/json/list`).then((response) => {
  if (!response.ok) throw new Error(`CDP page listing failed: ${response.status}`);
  return response.json();
});
const page = pages.find(
  (candidate) =>
    candidate.type === "page" && candidate.url.startsWith(listedOrigin),
);
if (!page) {
  throw new Error(`kiosk page for ${listedOrigin} was not found`);
}

const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve);
  socket.addEventListener("error", reject);
});

let nextId = 0;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  const resolve = pending.get(message.id);
  if (resolve) {
    pending.delete(message.id);
    resolve(message);
  }
});

const call = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, resolve);
    socket.send(JSON.stringify({ id, method, params }));
    setTimeout(() => {
      if (pending.delete(id)) reject(new Error(`CDP timeout: ${method}`));
    }, 10000);
  });

const permissionExpression = `
  (async () => {
    const result = { origin: location.origin };
    for (const name of ${JSON.stringify(permissionNames)}) {
      try {
        result[name] = (await navigator.permissions.query({ name })).state;
      } catch (error) {
        result[name] = "error:" + error.name;
      }
    }
    return result;
  })()
`;

const probeOrigin = async (origin) => {
  await call("Page.navigate", { url: `${origin}/` });
  await sleep(1500);
  const result = await call("Runtime.evaluate", {
    expression: permissionExpression,
    returnByValue: true,
    awaitPromise: true,
  });
  return result.result.result.value;
};

const listed = await probeOrigin(listedOrigin);
const unlisted = await probeOrigin(unlistedOrigin);
await call("Page.navigate", { url: `${listedOrigin}/` });
socket.close();

const listedGranted = permissionNames.every(
  (name) => listed.origin === listedOrigin && listed[name] === "granted",
);
const unlistedPrompt = permissionNames.every(
  (name) => unlisted.origin === unlistedOrigin && unlisted[name] === "prompt",
);
const evidence = {
  listed,
  unlisted,
  restored: listedOrigin,
  verdict: listedGranted && unlistedPrompt ? "PASS" : "FAIL",
};
console.log(JSON.stringify(evidence, null, 2));
if (evidence.verdict !== "PASS") process.exitCode = 1;
