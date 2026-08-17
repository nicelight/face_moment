import assert from "node:assert/strict";
import {
  DEFAULT_JPEG_QUALITY,
  JPEG_QUALITY_STORAGE_KEY,
  JPEG_QUALITY_VALUES,
  JpegQualityController,
  normalizeJpegQuality,
} from "../../client/jpeg-quality.js";

function createStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
    value(key) {
      return values.get(key) ?? null;
    },
  };
}

function provesExactAllowListAndDefault() {
  assert.deepEqual(JPEG_QUALITY_VALUES, [0.7, 0.75, 0.8, 0.85, 0.9, 0.95]);
  const storage = createStorage();
  const controller = new JpegQualityController({ storage });
  assert.equal(controller.getQuality(), DEFAULT_JPEG_QUALITY);
  assert.equal(storage.value(JPEG_QUALITY_STORAGE_KEY), null);

  for (const quality of JPEG_QUALITY_VALUES) {
    assert.equal(controller.setQuality(String(quality)), quality);
    assert.equal(storage.value(JPEG_QUALITY_STORAGE_KEY), String(quality));
  }

  assert.throws(() => normalizeJpegQuality("0.70"), /not_allowed/);
  assert.throws(() => controller.setQuality(0.77), /not_allowed/);
  assert.equal(controller.getQuality(), 0.95);
  assert.equal(storage.value(JPEG_QUALITY_STORAGE_KEY), "0.95");
}

function provesReloadReadsOnlyThePersistedAllowedSelection() {
  const storage = createStorage({ [JPEG_QUALITY_STORAGE_KEY]: "0.9" });
  const reloaded = new JpegQualityController({ storage });
  assert.equal(reloaded.getQuality(), 0.9);

  const invalid = createStorage({ [JPEG_QUALITY_STORAGE_KEY]: "0.91" });
  const fallback = new JpegQualityController({ storage: invalid });
  assert.equal(fallback.getQuality(), DEFAULT_JPEG_QUALITY);
  assert.equal(invalid.value(JPEG_QUALITY_STORAGE_KEY), null);
}

function provesActiveAttemptSnapshotDoesNotMutateAndNextAttemptUsesChange() {
  const storage = createStorage({ [JPEG_QUALITY_STORAGE_KEY]: "0.7" });
  const started = [];
  const controller = new JpegQualityController({
    storage,
    onAttemptStart: (snapshot) => started.push(snapshot),
  });

  const active = controller.startAttempt("attempt-one");
  assert.equal(active.jpegQuality, 0.7);
  assert.equal(Object.isFrozen(active), true);

  controller.setQuality(0.95);
  assert.equal(controller.getQuality(), 0.95);
  assert.equal(controller.getActiveAttemptSnapshot().jpegQuality, 0.7);
  assert.equal(controller.startAttempt("attempt-overlap").attemptId, "attempt-one");
  assert.equal(started.length, 1);

  controller.finishAttempt("attempt-one");
  const next = controller.startAttempt("attempt-two");
  assert.deepEqual(next, { attemptId: "attempt-two", jpegQuality: 0.95 });
  assert.equal(started.length, 2);
}

provesExactAllowListAndDefault();
provesReloadReadsOnlyThePersistedAllowedSelection();
provesActiveAttemptSnapshotDoesNotMutateAndNextAttemptUsesChange();
console.log(
  "jpeg quality GREEN: exact allow-list/default, local persistence, frozen active snapshot, next-Attempt application",
);
