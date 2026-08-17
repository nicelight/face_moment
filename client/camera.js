export const CAMERA_STORAGE_KEY = "face-moment.camera.device-id";

// The deployment may override this through __FACE_MOMENT_CAMERA_CONFIG__.
// The fallback is deliberately conservative; the pilot's exact site maximum
// remains deployment configuration rather than a product contract.
export const DEFAULT_CAMERA_MAX_DIMENSIONS = Object.freeze({
  width: 1280,
  height: 720,
});

function positiveDimension(value, name) {
  if (!Number.isFinite(value) || value <= 0) {
    throw new TypeError(`${name} must be a finite positive number`);
  }
  return value;
}

function sourceDimension(source, names, name) {
  for (const candidate of names) {
    if (Number.isFinite(source?.[candidate]) && source[candidate] > 0) {
      return source[candidate];
    }
  }
  throw new TypeError(`${name} must expose a finite positive image dimension`);
}

export function getFrameDimensions(source) {
  return {
    width: sourceDimension(
      source,
      ["videoWidth", "naturalWidth", "displayWidth", "width"],
      "source width",
    ),
    height: sourceDimension(
      source,
      ["videoHeight", "naturalHeight", "displayHeight", "height"],
      "source height",
    ),
  };
}

export function normalizeMaxDimensions(maxDimensions = DEFAULT_CAMERA_MAX_DIMENSIONS) {
  return {
    width: positiveDimension(maxDimensions?.width, "maxDimensions.width"),
    height: positiveDimension(maxDimensions?.height, "maxDimensions.height"),
  };
}

function makeCanvas(width, height, canvasFactory) {
  const canvas = canvasFactory?.(width, height);
  if (canvas) return canvas;

  if (typeof document !== "undefined") {
    const htmlCanvas = document.createElement("canvas");
    htmlCanvas.width = width;
    htmlCanvas.height = height;
    return htmlCanvas;
  }

  if (typeof OffscreenCanvas !== "undefined") {
    return new OffscreenCanvas(width, height);
  }

  throw new Error("browser_canvas_unavailable");
}

/**
 * Cap a camera frame before a ring buffer or detector receives it.
 * Dimensions are reduced proportionally and never enlarged.
 */
export function normalizeFrameForDownstream(
  source,
  { maxDimensions = DEFAULT_CAMERA_MAX_DIMENSIONS, canvasFactory } = {},
) {
  const sourceDimensions = getFrameDimensions(source);
  const limits = normalizeMaxDimensions(maxDimensions);
  const scale = Math.min(
    1,
    limits.width / sourceDimensions.width,
    limits.height / sourceDimensions.height,
  );
  const width = Math.max(1, Math.round(sourceDimensions.width * scale));
  const height = Math.max(1, Math.round(sourceDimensions.height * scale));

  if (scale === 1) {
    return {
      frame: source,
      sourceWidth: sourceDimensions.width,
      sourceHeight: sourceDimensions.height,
      width,
      height,
      scale,
      resized: false,
    };
  }

  const canvas = makeCanvas(width, height, canvasFactory);
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { alpha: false, colorSpace: "srgb" });
  if (!context) throw new Error("browser_2d_canvas_unavailable");
  context.drawImage(
    source,
    0,
    0,
    sourceDimensions.width,
    sourceDimensions.height,
    0,
    0,
    width,
    height,
  );

  return {
    frame: canvas,
    sourceWidth: sourceDimensions.width,
    sourceHeight: sourceDimensions.height,
    width,
    height,
    scale,
    resized: true,
  };
}

function safeStorage(storage) {
  if (storage) return storage;
  try {
    return globalThis.localStorage;
  } catch {
    return null;
  }
}

function readableLabel(device, index) {
  const label = String(device?.label ?? "").trim();
  return label || `Камера ${index + 1}`;
}

function videoDevices(devices) {
  return devices
    .filter((device) => device?.kind === "videoinput")
    .map((device, index) => ({
      deviceId: String(device.deviceId ?? ""),
      label: readableLabel(device, index),
      groupId: String(device.groupId ?? ""),
    }))
    .filter((device) => device.deviceId);
}

export class CameraController {
  constructor({
    mediaDevices = globalThis.navigator?.mediaDevices,
    storage,
    previewElement,
    maxDimensions = DEFAULT_CAMERA_MAX_DIMENSIONS,
    canvasFactory,
    onStateChange = () => {},
    onDevices = () => {},
    onError = () => {},
    onFrame = () => {},
  } = {}) {
    this.mediaDevices = mediaDevices;
    this.storage = safeStorage(storage);
    this.previewElement = previewElement ?? null;
    this.maxDimensions = normalizeMaxDimensions(maxDimensions);
    this.canvasFactory = canvasFactory;
    this.onStateChange = onStateChange;
    this.onDevices = onDevices;
    this.onError = onError;
    this.onFrame = onFrame;
    this.devices = [];
    this.selectedDeviceId = this.readSelectedDeviceId();
    this.stream = null;
    this.state = "idle";
    this.started = false;
    this.selectionRevision = 0;
    this.boundDeviceChange = () => {
      void this.handleDeviceChange();
    };
  }

  readSelectedDeviceId() {
    try {
      return this.storage?.getItem(CAMERA_STORAGE_KEY) || null;
    } catch {
      return null;
    }
  }

  persistSelectedDeviceId(deviceId) {
    try {
      this.storage?.setItem(CAMERA_STORAGE_KEY, deviceId);
    } catch {
      // Camera operation remains local and recoverable if storage is unavailable.
    }
  }

  selectedDevice() {
    return this.devices.find((device) => device.deviceId === this.selectedDeviceId) ?? null;
  }

  snapshot() {
    return {
      state: this.state,
      devices: this.devices.map((device) => ({ ...device })),
      selectedDeviceId: this.selectedDeviceId,
      selectedLabel: this.selectedDevice()?.label ?? null,
      stream: this.stream,
    };
  }

  setState(state, detail = {}) {
    this.state = state;
    this.onStateChange({ ...this.snapshot(), ...detail });
  }

  setPreviewElement(previewElement) {
    this.previewElement = previewElement ?? null;
    if (!this.previewElement) return;
    this.previewElement.autoplay = true;
    this.previewElement.muted = true;
    this.previewElement.playsInline = true;
    this.previewElement.srcObject = this.stream;
    if (this.stream && typeof this.previewElement.play === "function") {
      void this.previewElement.play().catch(() => {});
    }
  }

  async start() {
    if (this.started) return this.snapshot();
    this.started = true;
    if (
      !this.mediaDevices ||
      typeof this.mediaDevices.enumerateDevices !== "function" ||
      typeof this.mediaDevices.getUserMedia !== "function"
    ) {
      this.setState("unavailable", { reason: "media_devices_unavailable" });
      return this.snapshot();
    }
    this.mediaDevices.addEventListener?.("devicechange", this.boundDeviceChange);
    await this.refreshDevices({ applyStoredSelection: true });
    return this.snapshot();
  }

  async refreshDevices({ applyStoredSelection = false } = {}) {
    if (!this.mediaDevices?.enumerateDevices) {
      this.setState("unavailable", { reason: "enumeration_unavailable" });
      return [];
    }

    try {
      this.devices = videoDevices(await this.mediaDevices.enumerateDevices());
      this.onDevices(this.devices.map((device) => ({ ...device })));
    } catch (error) {
      this.onError(error);
      this.setState("recoverable-error", { reason: "enumeration_failed" });
      return [];
    }

    if (this.selectedDeviceId && !this.selectedDevice()) {
      this.requireReselection("selected_device_unavailable");
      return this.devices;
    }

    if (applyStoredSelection && this.selectedDeviceId) {
      try {
        await this.selectDevice(this.selectedDeviceId, { persist: false });
      } catch {
        this.requireReselection("stored_device_unavailable");
      }
      return this.devices;
    }

    if (!this.selectedDeviceId) {
      this.setState("selection-required", { reason: "no_explicit_selection" });
    }
    return this.devices;
  }

  async handleDeviceChange() {
    await this.refreshDevices({ applyStoredSelection: false });
  }

  stopPreview() {
    this.stopStream(this.stream);
    this.stream = null;
    if (this.previewElement) this.previewElement.srcObject = null;
  }

  stopStream(stream) {
    for (const track of stream?.getTracks?.() ?? []) track.stop();
  }

  requireReselection(reason) {
    this.selectionRevision += 1;
    this.stopPreview();
    this.setState("reselection-required", { reason });
  }

  async selectDevice(deviceId, { persist = true } = {}) {
    const requestedId = String(deviceId ?? "");
    const device = this.devices.find((candidate) => candidate.deviceId === requestedId);
    if (!device) throw new Error("camera_device_not_available");
    if (!this.mediaDevices?.getUserMedia) throw new Error("media_devices_unavailable");

    const selectionRevision = ++this.selectionRevision;
    this.selectedDeviceId = requestedId;
    this.stopPreview();
    this.setState("opening", { reason: "explicit_selection" });
    try {
      const stream = await this.mediaDevices.getUserMedia({
        audio: false,
        video: { deviceId: { exact: requestedId } },
      });
      if (selectionRevision !== this.selectionRevision) {
        this.stopStream(stream);
        return this.snapshot();
      }
      const track = stream?.getVideoTracks?.()[0];
      if (!track) {
        this.stopStream(stream);
        throw new Error("camera_video_track_missing");
      }
      track.addEventListener?.("ended", () => {
        if (this.stream === stream) this.requireReselection("selected_device_ended");
      });
      this.stream = stream;
      if (persist) this.persistSelectedDeviceId(requestedId);
      this.setPreviewElement(this.previewElement);
      this.setState("ready", { reason: "explicit_selection" });
      return this.snapshot();
    } catch (error) {
      if (selectionRevision !== this.selectionRevision) return this.snapshot();
      this.onError(error);
      this.requireReselection("selected_device_open_failed");
      throw error;
    }
  }

  captureFrame(source = this.previewElement) {
    if (!source) throw new Error("camera_preview_required");
    const normalized = normalizeFrameForDownstream(source, {
      maxDimensions: this.maxDimensions,
      canvasFactory: this.canvasFactory,
    });
    this.onFrame(normalized);
    return normalized;
  }

  destroy() {
    this.mediaDevices?.removeEventListener?.("devicechange", this.boundDeviceChange);
    this.started = false;
    this.selectionRevision += 1;
    this.stopPreview();
    this.setState("idle", { reason: "destroyed" });
  }
}

export function createCameraController(config) {
  return new CameraController(config);
}
