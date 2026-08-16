import { createSensorPassageClient } from "./sensor.js";
import { detectReferenceSeries } from "./blazeface.js";

const view = document.querySelector("#client-view");
let detectorFailureMessage = false;

const views = {
  advertising: {
    title: "Добро пожаловать",
    text: "Здесь будет локальная реклама и информация для гостей.",
    className: "advertising-card",
  },
  configuration: {
    title: "Конфигурация",
    text: "Настройки центрального клиента будут доступны в следующих этапах.",
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
render();

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
