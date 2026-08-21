import { createSensorPassageClient } from "./sensor.js";
import {
  readSensorConfig,
  saveSensorConfig,
} from "./sensor-config.js";
import {
  readDisplayClientToken,
  saveDisplayClientToken,
} from "./display-client-config.js";
import { detectReferenceSeries } from "./blazeface.js";
import { createCameraController } from "./camera.js";
import { createReferenceCaptureController } from "./trigger-series.js";
import {
  createJpegQualityController,
  JPEG_QUALITY_VALUES,
} from "./jpeg-quality.js";
import { createAttemptOutcomeController } from "./attempt-outcome.js";
import { submitRealtimeAttempt } from "./realtime-attempt.js";
import { createAttemptTimingRecorder } from "./attempt-timing.js";

const view = document.querySelector("#client-view");
let detectorFailureMessage = false;
let cameraController;
let sensorClient;
let triggerController;
let attemptOutcomeController;
const jpegQualityController = createJpegQualityController({
  onChange: updateQualityConfiguration,
});

const views = {
  advertising: {
    title: "Добро пожаловать",
    text: "Здесь будет локальная реклама и информация для гостей.",
    className: "advertising-card",
  },
  configuration: {
    title: "Конфигурация",
    text: "Настройте сенсор и выберите камеру явно для предварительного просмотра и захвата.",
    className: "configuration-card",
  },
  debug: {
    title: "Диагностика",
    text: "Состояние клиента и диагностические сведения появятся в следующих этапах.",
    className: "debug-card",
  },
};

function currentView() {
  const requested = window.location.hash.slice(1);
  return Object.hasOwn(views, requested) ? requested : "advertising";
}

function render() {
  if (!view) return;
  const name = currentView();
  const content = views[name];
  view.replaceChildren();

  const card = document.createElement("section");
  card.className = `view-card ${content.className}`;
  card.dataset.view = name;

  const title = document.createElement("h2");
  title.textContent = content.title;
  card.append(title);

  const text = document.createElement("p");
  text.textContent = content.text;
  card.append(text);

  view.append(card);
  if (name === "configuration") mountDisplayClientConfiguration(card);
  if (name === "configuration") mountSensorConfiguration(card);
  if (name === "configuration") mountQualityConfiguration(card);
  if (name === "configuration") mountCameraConfiguration(card);
  if (name === "configuration") mountTriggerConfiguration(card);
  if (name === "advertising" && detectorFailureMessage) {
    const notice = document.createElement("p");
    notice.className = "notice";
    notice.dataset.detectorError = "true";
    notice.setAttribute("role", "alert");
    notice.textContent =
      "Детектор лиц временно недоступен. Клиент продолжает рекламу; оператор может повторить попытку.";
    card.append(notice);
  }
}

function displayClientStatusMessage() {
  return readDisplayClientToken()
    ? "Центральный токен сохранён в профиле этого киоска."
    : "Центральный токен не настроен. Реклама продолжает работать.";
}

function mountDisplayClientConfiguration(card) {
  const panel = document.createElement("div");
  panel.className = "display-client-panel";
  panel.dataset.displayClientPanel = "true";

  const heading = document.createElement("h3");
  heading.textContent = "Центральный токен киоска";
  panel.append(heading);

  const help = document.createElement("p");
  help.textContent = "Скопируйте текущий токен из настроек администратора и вставьте его вручную для этого киоска.";
  panel.append(help);

  const label = document.createElement("label");
  label.htmlFor = "display-client-token";
  label.textContent = "Токен центрального экрана";
  panel.append(label);

  const input = document.createElement("input");
  input.id = "display-client-token";
  input.type = "password";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.placeholder = "Вставьте токен вручную";
  panel.append(input);

  const save = document.createElement("button");
  save.id = "display-client-save";
  save.type = "button";
  save.textContent = "Сохранить токен в профиле";
  panel.append(save);

  const status = document.createElement("p");
  status.id = "display-client-status";
  status.className = "display-client-status";
  status.setAttribute("role", "status");
  status.textContent = displayClientStatusMessage();
  panel.append(status);
  card.append(panel);

  save.addEventListener("click", () => {
    try {
      saveDisplayClientToken(input.value);
      input.value = "";
      status.textContent = "Токен сохранён в профиле; запросы используют только Authorization Bearer.";
      document.body.dataset.displayClientState = "configured";
      window.dispatchEvent(
        new CustomEvent("face-moment:display-client-configured", {
          detail: { configured: true },
        }),
      );
    } catch {
      status.textContent = "Введите непустой токен без управляющих символов.";
      document.body.dataset.displayClientState = "recoverable-error";
    }
  });

  document.body.dataset.displayClientState = readDisplayClientToken()
    ? "configured"
    : "unconfigured";
}

function sensorStateMessage(state) {
  if (state === "disabled") return "Сенсор не настроен. Реклама продолжает работать.";
  if (state === "polling") return "Ожидаем событие сенсора.";
  if (state === "passage") return "Событие сенсора получено.";
  if (state === "advertising") return "Сенсор доступен. Реклама продолжает работать.";
  if (state === "recoverable-error") {
    return "Сенсор временно недоступен. Реклама продолжает работать.";
  }
  return "Сенсор запускается.";
}

function updateSensorStatus(state, message) {
  document.body.dataset.sensorState = state;
  const status = document.querySelector("#sensor-status");
  if (status) status.textContent = message ?? sensorStateMessage(state);
}

function stopSensorClient() {
  sensorClient?.stop();
  sensorClient = null;
}

function startSensorClient(config) {
  stopSensorClient();
  if (!config) {
    updateSensorStatus("disabled");
    return false;
  }

  try {
    sensorClient = createSensorPassageClient({
      ...config,
      onEvent: (event) => {
        window.dispatchEvent(
          new CustomEvent("face-moment:sensor-passage", { detail: event }),
        );
      },
      onStatus: (status) => updateSensorStatus(status),
    });
    sensorClient.start();
    updateSensorStatus("polling");
    return true;
  } catch {
    updateSensorStatus("recoverable-error");
    return false;
  }
}

function updateTriggerStatus(state, message) {
  document.body.dataset.triggerState = state;
  const status = document.querySelector("#trigger-status");
  if (status) status.textContent = message;
}

function restoreAdvertisingAfterFailure(detail) {
  if (detail?.state !== "advertising" || detail?.handled !== true) return;
  window.dispatchEvent(
    new CustomEvent("face-moment:attempt-finished", {
      detail: {
        attemptId: detail.captureId ?? detail.attemptId,
        success: false,
        reason: detail.reason ?? "unsuccessful",
      },
    }),
  );
}

function newRealtimeAttemptId() {
  const attemptId = globalThis.crypto?.randomUUID?.();
  if (typeof attemptId !== "string" || !attemptId) {
    throw new Error("crypto_random_uuid_unavailable");
  }
  return attemptId;
}

async function submitReadyReferenceSeries(detail, proposals) {
  const captureId = detail?.attemptId;
  let attemptId;
  let timingRecorder;
  try {
    attemptId = newRealtimeAttemptId();
    timingRecorder = createAttemptTimingRecorder({
      attemptId,
      captureId,
      referenceSeriesReadyMonotonicMs:
        detail?.reference_series_ready_at_ms,
    });
    timingRecorder.recordLocalDetectionCompleted();
    timingRecorder.recordRequestStarted();
    window.dispatchEvent(
      new CustomEvent("face-moment:attempt-request-start", {
        detail: { attemptId, captureId, timing: timingRecorder.snapshot() },
      }),
    );

    const qualitySnapshot = jpegQualityController.getActiveAttemptSnapshot();
    const cameraSnapshot = cameraController?.snapshot?.() ?? {};
    const submitted = await submitRealtimeAttempt({
      attemptId,
      triggerSource: detail?.trigger_source,
      jpegQuality: qualitySnapshot?.jpegQuality,
      cameraDeviceId: cameraSnapshot.selectedDeviceId,
      clientToken: readDisplayClientToken(),
      timing: timingRecorder.manifestTiming(),
      frames: detail?.frames,
      frameTimestampsMs: detail?.frame_timestamps_ms,
      proposals,
    });
    timingRecorder.recordResponseReceived();
    window.dispatchEvent(
      new CustomEvent("face-moment:attempt-response", {
        detail: {
          attemptId,
          captureId,
          response: submitted.response,
          timing: timingRecorder.snapshot(),
        },
      }),
    );
  } catch {
    if (attemptId) {
      window.dispatchEvent(
        new CustomEvent("face-moment:attempt-transport-failure", {
          detail: {
            attemptId,
            captureId,
            timing: timingRecorder?.snapshot(),
          },
        }),
      );
    } else {
      window.dispatchEvent(
        new CustomEvent("face-moment:attempt-finished", {
          detail: {
            attemptId: captureId,
            success: false,
            reason: "request_setup_failure",
          },
        }),
      );
    }
  }
}

window.addEventListener("face-moment:attempt-request-start", (event) => {
  try {
    attemptOutcomeController?.beginAttempt({
      attemptId: event.detail?.attemptId,
      captureId: event.detail?.captureId,
    });
  } catch {
    document.body.dataset.attemptState =
      attemptOutcomeController?.state ?? "advertising";
  }
});

window.addEventListener("face-moment:attempt-response", (event) => {
  const pending = attemptOutcomeController?.handleResponse(
    event.detail?.attemptId,
    event.detail?.response,
  );
  if (pending) {
    void pending.then((detail) =>
      restoreAdvertisingAfterFailure({
        ...detail,
        captureId: event.detail?.captureId,
      }),
    );
  }
});

window.addEventListener("face-moment:attempt-transport-failure", (event) => {
  const result = attemptOutcomeController?.handleTransportFailure(
    event.detail?.attemptId,
  );
  restoreAdvertisingAfterFailure({
    ...result,
    captureId: event.detail?.captureId,
  });
});

function mountTriggerConfiguration(card) {
  const panel = document.createElement("div");
  panel.className = "trigger-panel";
  panel.dataset.triggerPanel = "true";

  const heading = document.createElement("h3");
  heading.textContent = "Тестирование срабатывания";
  panel.append(heading);

  const testTrigger = document.createElement("button");
  testTrigger.id = "test-trigger";
  testTrigger.type = "button";
  testTrigger.textContent = "Тестовое срабатывание сенсора";
  testTrigger.addEventListener("click", () => {
    window.dispatchEvent(
      new CustomEvent("face-moment:trigger-request", {
        detail: { trigger_source: "test", requested_from: "configuration" },
      }),
    );
  });
  panel.append(testTrigger);

  const status = document.createElement("p");
  status.id = "trigger-status";
  status.className = "trigger-status";
  status.setAttribute("role", "status");
  status.textContent = "Реклама активна; ожидаем срабатывание.";
  panel.append(status);
  card.append(panel);
}

function mountSensorConfiguration(card) {
  const panel = document.createElement("div");
  panel.className = "sensor-panel";
  panel.dataset.sensorPanel = "true";

  const heading = document.createElement("h3");
  heading.textContent = "Датчик прохода";
  panel.append(heading);

  const hostLabel = document.createElement("label");
  hostLabel.htmlFor = "sensor-host";
  hostLabel.textContent = "Адрес сенсора";
  panel.append(hostLabel);

  const hostInput = document.createElement("input");
  hostInput.id = "sensor-host";
  hostInput.name = "sensor-host";
  hostInput.type = "text";
  hostInput.autocomplete = "off";
  hostInput.placeholder = "fm-sensor1.local";
  panel.append(hostInput);

  const idLabel = document.createElement("label");
  idLabel.htmlFor = "sensor-id";
  idLabel.textContent = "Стабильный ID сенсора";
  panel.append(idLabel);

  const idInput = document.createElement("input");
  idInput.id = "sensor-id";
  idInput.name = "sensor-id";
  idInput.type = "text";
  idInput.autocomplete = "off";
  idInput.placeholder = "fm-sensor1";
  panel.append(idInput);

  const secretLabel = document.createElement("label");
  secretLabel.htmlFor = "sensor-secret";
  secretLabel.textContent = "Bearer secret";
  panel.append(secretLabel);

  const secretInput = document.createElement("input");
  secretInput.id = "sensor-secret";
  secretInput.name = "sensor-secret";
  secretInput.type = "password";
  secretInput.autocomplete = "new-password";
  panel.append(secretInput);

  const save = document.createElement("button");
  save.id = "sensor-save";
  save.type = "button";
  save.textContent = "Сохранить и запустить сенсор";
  panel.append(save);

  const status = document.createElement("p");
  status.id = "sensor-status";
  status.className = "sensor-status";
  status.setAttribute("role", "status");
  panel.append(status);
  card.append(panel);

  const stored = readSensorConfig();
  if (stored) {
    hostInput.value = stored.host;
    idInput.value = stored.sensorId;
    secretInput.placeholder = "Сохранённый secret; оставьте пустым, чтобы сохранить его";
  }

  save.addEventListener("click", () => {
    const current = readSensorConfig();
    try {
      const config = saveSensorConfig({
        host: hostInput.value,
        sensorId: idInput.value,
        secret: secretInput.value || current?.secret,
      });
      secretInput.value = "";
      secretInput.placeholder = "Сохранённый secret; оставьте пустым, чтобы сохранить его";
      const started = startSensorClient(config);
      status.textContent = started
        ? "Конфигурация сохранена; сенсор запущен."
        : "Конфигурация сохранена, но сенсор недоступен. Реклама продолжает работать.";
    } catch {
      updateSensorStatus("recoverable-error", "Проверьте адрес, ID и Bearer secret.");
    }
  });

  updateSensorStatus(
    document.body.dataset.sensorState ?? "disabled",
    sensorStateMessage(document.body.dataset.sensorState ?? "disabled"),
  );
}

function updateQualityConfiguration() {
  const select = document.querySelector("#jpeg-quality");
  const status = document.querySelector("#jpeg-quality-status");
  if (!select || !status) return;

  select.value = String(jpegQualityController.getQuality());
  status.textContent = "Изменение применяется со следующей попытки.";
  document.body.dataset.jpegQuality = String(jpegQualityController.getQuality());
}

function mountQualityConfiguration(card) {
  const panel = document.createElement("div");
  panel.className = "quality-panel";
  panel.dataset.qualityPanel = "true";

  const label = document.createElement("label");
  label.htmlFor = "jpeg-quality";
  label.textContent = "Качество JPEG";
  panel.append(label);

  const select = document.createElement("select");
  select.id = "jpeg-quality";
  select.name = "jpeg-quality";
  for (const quality of JPEG_QUALITY_VALUES) {
    const option = document.createElement("option");
    option.value = String(quality);
    option.textContent = String(quality);
    select.append(option);
  }
  select.addEventListener("change", () => {
    try {
      jpegQualityController.setQuality(select.value);
      updateQualityConfiguration();
    } catch {
      updateQualityConfiguration();
    }
  });
  panel.append(select);

  const status = document.createElement("p");
  status.id = "jpeg-quality-status";
  status.className = "quality-status";
  status.setAttribute("role", "status");
  panel.append(status);
  card.append(panel);
  updateQualityConfiguration();
}

function cameraStateMessage(state) {
  if (state === "ready") return "Камера выбрана и доступна для предпросмотра.";
  if (state === "opening") return "Открываем выбранную камеру…";
  if (state === "reselection-required") {
    return "Выбранная камера недоступна. Выберите её снова; другая камера автоматически не включается.";
  }
  if (state === "selection-required") return "Выберите камеру явно.";
  if (state === "unavailable") return "Камера недоступна. Реклама продолжает работать.";
  if (state === "recoverable-error") return "Список камер временно недоступен. Реклама продолжает работать.";
  return "Список камер загружается.";
}

function updateCameraConfiguration() {
  const panel = document.querySelector("[data-camera-panel]");
  const select = document.querySelector("#camera-device");
  const status = document.querySelector("#camera-status");
  if (!panel || !select || !status || !cameraController) return;

  const selectedId = cameraController.selectedDeviceId;
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Выберите камеру";
  placeholder.disabled = true;
  placeholder.selected = !selectedId;
  select.append(placeholder);
  for (const device of cameraController.devices) {
    const option = document.createElement("option");
    option.value = device.deviceId;
    option.textContent = device.label;
    option.selected = device.deviceId === selectedId;
    select.append(option);
  }
  status.textContent = cameraStateMessage(cameraController.state);
  panel.dataset.cameraState = cameraController.state;
  document.body.dataset.cameraState = cameraController.state;
}

function mountCameraConfiguration(card) {
  const panel = document.createElement("div");
  panel.className = "camera-panel";
  panel.dataset.cameraPanel = "true";

  const label = document.createElement("label");
  label.htmlFor = "camera-device";
  label.textContent = "Камера";
  panel.append(label);

  const select = document.createElement("select");
  select.id = "camera-device";
  select.name = "camera-device";
  select.addEventListener("change", async () => {
    try {
      await cameraController.selectDevice(select.value);
    } catch {
      updateCameraConfiguration();
    }
  });
  panel.append(select);

  const refresh = document.createElement("button");
  refresh.type = "button";
  refresh.textContent = "Обновить список";
  refresh.addEventListener("click", () => {
    void cameraController.refreshDevices();
  });
  panel.append(refresh);

  const preview = document.createElement("video");
  preview.id = "camera-preview";
  preview.className = "camera-preview";
  preview.autoplay = true;
  preview.muted = true;
  preview.playsInline = true;
  preview.setAttribute("aria-label", "Предварительный просмотр выбранной камеры");
  panel.append(preview);

  const status = document.createElement("p");
  status.id = "camera-status";
  status.className = "camera-status";
  status.setAttribute("role", "status");
  panel.append(status);
  card.append(panel);

  cameraController.setPreviewElement(preview);
  updateCameraConfiguration();
}

function renderDetectorFailure() {
  detectorFailureMessage = true;
  document.body.dataset.detectorState = "recoverable-error";
  if (currentView() !== "advertising") {
    window.location.hash = "#advertising";
  } else {
    render();
  }
}

function copyCameraFrame(captured) {
  const source = captured?.frame ?? captured?.image;
  if (!source || typeof document === "undefined") return captured;
  const width = captured.width ?? source.videoWidth ?? source.width;
  const height = captured.height ?? source.videoHeight ?? source.height;
  if (!Number.isFinite(width) || !Number.isFinite(height)) return captured;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { alpha: false, colorSpace: "srgb" });
  if (!context) return captured;
  context.drawImage(source, 0, 0, width, height);
  return {
    ...captured,
    image: canvas,
    frame: canvas,
    timestampMs: undefined,
  };
}

window.addEventListener("hashchange", render);

window.addEventListener("face-moment:sensor-passage", (event) => {
  window.dispatchEvent(
    new CustomEvent("face-moment:trigger-request", {
      detail: { trigger_source: "physical", sensor_event: event.detail },
    }),
  );
});

window.addEventListener("face-moment:trigger-request", (event) => {
  const source = event.detail?.trigger_source;
  const result = triggerController?.acceptTrigger(source, event.detail) ?? {
    accepted: false,
    reason: "client_unavailable",
  };
  if (result.accepted) {
    updateTriggerStatus(
      "capturing",
      `${source === "test" ? "Тестовое" : "Физическое"} срабатывание принято; формируем серию.`,
    );
  } else if (result.reason === "busy") {
    updateTriggerStatus("busy", "Срабатывание проигнорировано: текущая попытка ещё выполняется.");
  } else {
    updateTriggerStatus("unavailable", "Камера не готова; реклама продолжает работать.");
  }
});

window.addEventListener("face-moment:attempt-finished", (event) => {
  triggerController?.finishAttempt({
    success: event.detail?.success === true,
    cooldownMs: event.detail?.cooldownMs ?? 0,
  });
});

window.addEventListener("face-moment:attempt-start", (event) => {
  const snapshot = jpegQualityController.startAttempt(event.detail?.attemptId);
  document.body.dataset.activeAttemptJpegQuality = String(snapshot.jpegQuality);
  window.dispatchEvent(
    new CustomEvent("face-moment:attempt-quality-snapshot", {
      detail: snapshot,
    }),
  );
});

window.addEventListener("face-moment:attempt-finished", (event) => {
  jpegQualityController.finishAttempt(event.detail?.attemptId);
  delete document.body.dataset.activeAttemptJpegQuality;
});

window.addEventListener("face-moment:reference-series-ready", async (event) => {
  try {
    const proposals = await detectReferenceSeries(event.detail?.frames);
    document.body.dataset.detectorState = "ready";
    window.dispatchEvent(
      new CustomEvent("face-moment:proposals-ready", {
        detail: { proposals },
      }),
    );
    void submitReadyReferenceSeries(event.detail, proposals);
  } catch (error) {
    renderDetectorFailure();
    window.dispatchEvent(
      new CustomEvent("face-moment:detector-failure", {
        detail: { code: error?.code ?? "blazeface_unavailable" },
      }),
    );
  }
});

const cameraConfig = globalThis.__FACE_MOMENT_CAMERA_CONFIG__ ?? {};
cameraController = createCameraController({
  maxDimensions: cameraConfig.maxDimensions,
  onStateChange: updateCameraConfiguration,
  onDevices: updateCameraConfiguration,
  onError: () => updateCameraConfiguration(),
});
attemptOutcomeController = createAttemptOutcomeController({
  onStateChange: ({ state, outcome }) => {
    document.body.dataset.attemptState = state;
    if (outcome) document.body.dataset.attemptOutcome = outcome;
  },
  onOutcome: (detail) => {
    window.dispatchEvent(
      new CustomEvent("face-moment:attempt-outcome", { detail }),
    );
  },
});
triggerController = createReferenceCaptureController({
  captureFrame: () => {
    if (cameraController?.state !== "ready") return null;
    return cameraController.captureFrame();
  },
  cloneFrame: copyCameraFrame,
  onAttemptStart: (detail) => {
    window.dispatchEvent(new CustomEvent("face-moment:attempt-start", { detail }));
  },
  onReferenceSeriesReady: (detail) => {
    updateTriggerStatus("searching", "Серия готова; начинаем локальную обработку.");
    window.dispatchEvent(
      new CustomEvent("face-moment:reference-series-ready", { detail }),
    );
  },
  onIgnoredTrigger: (detail) => {
    updateTriggerStatus(
      detail.reason,
      detail.reason === "busy"
        ? "Срабатывание проигнорировано: текущая попытка ещё выполняется."
        : "Камера не готова; реклама продолжает работать.",
    );
    window.dispatchEvent(new CustomEvent("face-moment:trigger-ignored", { detail }));
  },
  onStateChange: ({ state }) => {
    if (state === "advertising") {
      updateTriggerStatus("advertising", "Реклама активна; ожидаем срабатывание.");
    }
  },
});
render();
triggerController.start();
void cameraController.start();
startSensorClient(readSensorConfig());
