import assert from "node:assert/strict";

const values = new Map();
globalThis.localStorage = {
  getItem(key) {
    return values.has(key) ? values.get(key) : null;
  },
  setItem(key, value) {
    values.set(key, String(value));
  },
  removeItem(key) {
    values.delete(key);
  },
};

const {
  DISPLAY_CLIENT_TOKEN_STORAGE_KEY,
  clearDisplayClientToken,
  getDisplayAuthorization,
  getDisplayRequestHeaders,
  readDisplayClientToken,
  saveDisplayClientToken,
} = await import("../../client/display-client-config.js");

assert.equal(readDisplayClientToken(), null);
assert.equal(getDisplayAuthorization(), null);
assert.deepEqual(getDisplayRequestHeaders({ "X-Test": "1" }), { "X-Test": "1" });

const firstToken = `fixture-display-token-${"a".repeat(32)}`;
assert.equal(saveDisplayClientToken(`  ${firstToken}  `), firstToken);
assert.equal(values.get(DISPLAY_CLIENT_TOKEN_STORAGE_KEY), firstToken);
assert.equal(readDisplayClientToken(), firstToken);
assert.equal(getDisplayAuthorization(), `Bearer ${firstToken}`);
assert.deepEqual(getDisplayRequestHeaders({ "X-Test": "1" }), {
  "X-Test": "1",
  Authorization: `Bearer ${firstToken}`,
});

const replacementToken = `fixture-replacement-token-${"b".repeat(32)}`;
saveDisplayClientToken(replacementToken);
assert.equal(readDisplayClientToken(), replacementToken);
assert.equal(getDisplayAuthorization(), `Bearer ${replacementToken}`);

assert.throws(() => saveDisplayClientToken(""), /display_client_token_invalid/);
assert.throws(() => saveDisplayClientToken("token\nleak"), /display_client_token_invalid/);

clearDisplayClientToken();
assert.equal(readDisplayClientToken(), null);
assert.equal(getDisplayAuthorization(), null);
console.log("display client config GREEN: profile persistence, replacement and Authorization-only accessor");
