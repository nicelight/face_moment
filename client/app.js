import { createSensorPassageClient } from "./sensor.js";
import { detectReferenceSeries } from "./blazeface.js";
import { createCameraController } from "./camera.js";
import {
  createJpegQualityController,
  JPEG_QUALITY_VALUES,
} from "./jpeg-quality.js";

const view = document.querySelector("#client-view");
let detectorFailureMessage = false;
let cameraController;
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
    text: "Выберите камеру явно для предварительного просмотра и захвата.",
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
  if (name === "configuration") mountQualityConfiguration(card);
  if (name === "configuration") mountCameraConfiguration(card);
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

window.addEventListener("hashchange", render);

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
  } catch (error) {
    renderDetectorFailure();
    window.dispatchEvent(
      new CustomEvent("face-moment:detector-failure", {
        detail: { code: error?.code ?? "blazeface_unavailable" },
      }),
    );
  }
});

const sensorConfig = globalThis.__FACE_MOMENT_SENSOR_CONFIG__;
if (sensorConfig) {
  try {
    const sensor = createSensorPassageClient({
      ...sensorConfig,
      onEvent: (event) => {
        window.dispatchEvent(
          new CustomEvent("face-moment:sensor-passage", { detail: event }),
        );
      },
      onStatus: (status) => {
        document.body.dataset.sensorState = status;
      },
    });
    sensor.start();
  } catch {
    document.body.dataset.sensorState = "recoverable-error";
  }
}

const cameraConfig = globalThis.__FACE_MOMENT_CAMERA_CONFIG__ ?? {};
cameraController = createCameraController({
  maxDimensions: cameraConfig.maxDimensions,
  onStateChange: updateCameraConfiguration,
  onDevices: updateCameraConfiguration,
  onError: () => updateCameraConfiguration(),
});
render();
void cameraController.start();
