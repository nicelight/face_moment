import assert from "node:assert/strict";
import {
  CAMERA_STORAGE_KEY,
  CameraController,
  DEFAULT_CAMERA_MAX_DIMENSIONS,
  normalizeFrameForDownstream,
} from "../../client/camera.js";

function createStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    value(key) {
      return values.get(key) ?? null;
    },
  };
}

function createMediaDevices(initialDevices) {
  const listeners = new Map();
  const calls = [];
  const mediaDevices = {
    devices: initialDevices,
    calls,
    async enumerateDevices() {
      return this.devices.map((device) => ({ ...device }));
    },
    async getUserMedia(constraints) {
      const requestedId = constraints.video.deviceId.exact;
      calls.push(requestedId);
      if (!this.devices.some((device) => device.deviceId === requestedId)) {
        throw new Error("fixture_device_missing");
      }
      return createStream(requestedId);
    },
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    removeEventListener(type) {
      listeners.delete(type);
    },
    emit(type) {
      listeners.get(type)?.();
    },
  };
  return mediaDevices;
}

function createDeferredMediaDevices(initialDevices) {
  const pending = new Map();
  const calls = [];
  const mediaDevices = {
    devices: initialDevices,
    calls,
    async enumerateDevices() {
      return this.devices.map((device) => ({ ...device }));
    },
    getUserMedia(constraints) {
      const requestedId = constraints.video.deviceId.exact;
      calls.push(requestedId);
      return new Promise((resolve, reject) => {
        pending.set(requestedId, { resolve, reject });
      });
    },
    resolve(deviceId) {
      const request = pending.get(deviceId);
      assert.ok(request, `no pending request for ${deviceId}`);
      const stream = createStream(deviceId);
      request.resolve(stream);
      return stream;
    },
  };
  return mediaDevices;
}

function createStream(deviceId) {
  const trackListeners = new Map();
  const track = {
    kind: "video",
    stopped: false,
    stop() {
      this.stopped = true;
    },
    addEventListener(type, listener) {
      trackListeners.set(type, listener);
    },
    emit(type) {
      trackListeners.get(type)?.();
    },
    getSettings() {
      return { deviceId };
    },
  };
  return {
    track,
    getVideoTracks() {
      return [track];
    },
    getTracks() {
      return [track];
    },
  };
}

function createVideo() {
  return {
    srcObject: null,
    playCalls: 0,
    play() {
      this.playCalls += 1;
      return Promise.resolve();
    },
  };
}

function videoDevice(deviceId, label, kind = "videoinput") {
  return { deviceId, label, kind, groupId: `${deviceId}-group` };
}

async function provesBrowserVisibleListAndExplicitPersistedPreview() {
  const storage = createStorage();
  const mediaDevices = createMediaDevices([
    videoDevice("front", "Встроенная камера"),
    videoDevice("mic", "Не камера", "audioinput"),
    videoDevice("usb", "USB UVC камера"),
  ]);
  const video = createVideo();
  const states = [];
  const controller = new CameraController({
    mediaDevices,
    storage,
    previewElement: video,
    onStateChange: (state) => states.push(state),
  });

  await controller.start();
  assert.deepEqual(
    controller.devices.map(({ deviceId, label }) => [deviceId, label]),
    [
      ["front", "Встроенная камера"],
      ["usb", "USB UVC камера"],
    ],
  );
  assert.equal(controller.state, "selection-required");
  assert.equal(mediaDevices.calls.length, 0);

  await controller.selectDevice("usb");
  assert.deepEqual(mediaDevices.calls, ["usb"]);
  assert.equal(storage.value(CAMERA_STORAGE_KEY), "usb");
  assert.equal(video.srcObject.track.getSettings().deviceId, "usb");
  assert.equal(video.playCalls, 1);
  assert.equal(controller.state, "ready");
  assert.equal(states.at(-1).selectedLabel, "USB UVC камера");
}

async function provesReloadAppliesOnlyThePersistedExactDevice() {
  const storage = createStorage({ [CAMERA_STORAGE_KEY]: "usb" });
  const mediaDevices = createMediaDevices([
    videoDevice("front", "Встроенная камера"),
    videoDevice("usb", "USB UVC камера"),
  ]);
  const controller = new CameraController({ mediaDevices, storage });

  await controller.start();
  assert.deepEqual(mediaDevices.calls, ["usb"]);
  assert.equal(controller.state, "ready");
}

async function provesLossKeepsAdvertisingAndRequiresReselectionWithoutFallback() {
  const storage = createStorage({ [CAMERA_STORAGE_KEY]: "usb" });
  const mediaDevices = createMediaDevices([
    videoDevice("usb", "USB UVC камера"),
    videoDevice("other", "Резервная камера"),
  ]);
  const states = [];
  const controller = new CameraController({
    mediaDevices,
    storage,
    onStateChange: (state) => states.push(state),
  });

  await controller.start();
  const firstStream = controller.stream;
  mediaDevices.devices = [videoDevice("other", "Резервная камера")];
  mediaDevices.emit("devicechange");
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(controller.state, "reselection-required");
  assert.equal(firstStream.track.stopped, true);
  assert.deepEqual(mediaDevices.calls, ["usb"]);
  assert.equal(states.at(-1).reason, "selected_device_unavailable");

  mediaDevices.devices = [videoDevice("usb-reconnected", "USB UVC камера снова")];
  mediaDevices.emit("devicechange");
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(controller.state, "reselection-required");
  assert.deepEqual(mediaDevices.calls, ["usb"]);

  await controller.selectDevice("usb-reconnected");
  assert.deepEqual(mediaDevices.calls, ["usb", "usb-reconnected"]);
  assert.equal(storage.value(CAMERA_STORAGE_KEY), "usb-reconnected");
  assert.equal(controller.state, "ready");
}

async function provesLatestExplicitSelectionInvalidatesLateMediaResult() {
  const storage = createStorage();
  const mediaDevices = createDeferredMediaDevices([
    videoDevice("a", "Камера A"),
    videoDevice("b", "Камера B"),
  ]);
  const controller = new CameraController({ mediaDevices, storage });

  await controller.start();
  const firstSelection = controller.selectDevice("a");
  const secondSelection = controller.selectDevice("b");
  const streamB = mediaDevices.resolve("b");
  const streamA = mediaDevices.resolve("a");
  await Promise.all([firstSelection, secondSelection]);

  console.log(
    "selection race probe:",
    JSON.stringify({
      selectedDeviceId: controller.selectedDeviceId,
      streamDeviceId: controller.stream?.getVideoTracks?.()[0]?.getSettings?.().deviceId,
      stored: storage.value(CAMERA_STORAGE_KEY),
      state: controller.state,
      staleTrackStopped: streamA.track.stopped,
    }),
  );
  assert.deepEqual(mediaDevices.calls, ["a", "b"]);
  assert.equal(controller.selectedDeviceId, "b");
  assert.equal(controller.stream, streamB);
  assert.equal(controller.stream.track.getSettings().deviceId, "b");
  assert.equal(storage.value(CAMERA_STORAGE_KEY), "b");
  assert.equal(streamA.track.stopped, true);
  assert.equal(controller.state, "ready");
}

function provesOversizedFramesAreCappedBeforeDownstream() {
  const draws = [];
  const canvasFactory = (width, height) => ({
    width,
    height,
    getContext() {
      return {
        drawImage(...args) {
          draws.push(args);
        },
      };
    },
  });
  const source = { videoWidth: 2560, videoHeight: 1440 };
  const result = normalizeFrameForDownstream(source, {
    maxDimensions: { width: 1280, height: 720 },
    canvasFactory,
  });

  assert.deepEqual(
    {
      sourceWidth: result.sourceWidth,
      sourceHeight: result.sourceHeight,
      width: result.width,
      height: result.height,
      resized: result.resized,
    },
    {
      sourceWidth: 2560,
      sourceHeight: 1440,
      width: 1280,
      height: 720,
      resized: true,
    },
  );
  assert.equal(result.frame.width, 1280);
  assert.equal(result.frame.height, 720);
  assert.deepEqual(draws, [[source, 0, 0, 2560, 1440, 0, 0, 1280, 720]]);

  const small = normalizeFrameForDownstream(
    { videoWidth: 640, videoHeight: 480 },
    { maxDimensions: DEFAULT_CAMERA_MAX_DIMENSIONS, canvasFactory },
  );
  assert.equal(small.resized, false);
  assert.equal(small.frame.videoWidth, 640);

  const downstreamFrames = [];
  const controller = new CameraController({
    maxDimensions: { width: 1280, height: 720 },
    previewElement: source,
    canvasFactory,
    onFrame: (frame) => downstreamFrames.push(frame),
  });
  const emitted = controller.captureFrame();
  assert.equal(emitted.width, 1280);
  assert.equal(emitted.height, 720);
  assert.equal(downstreamFrames[0].frame.width, 1280);
}

await provesBrowserVisibleListAndExplicitPersistedPreview();
await provesReloadAppliesOnlyThePersistedExactDevice();
await provesLossKeepsAdvertisingAndRequiresReselectionWithoutFallback();
await provesLatestExplicitSelectionInvalidatesLateMediaResult();
provesOversizedFramesAreCappedBeforeDownstream();
console.log(
  "camera GREEN: browser-visible list, exact persisted preview, explicit recovery reselection, and pre-downstream dimension cap",
);
